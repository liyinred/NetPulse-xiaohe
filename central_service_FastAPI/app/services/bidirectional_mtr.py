"""双向 MTR 任务编排服务。"""

from ipaddress import ip_address
import secrets
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.bidirectional_mtr import BidirectionalMTRDirection, BidirectionalMTRTask
from app.models.device import Device
from app.models.ip_dict import IPDict
from app.schemas.bidirectional_mtr import CreateMTRData, MTRAgentTask, MTRDevice, MTRDeviceIP, MTRTaskResult, MTRResultRequest
from app.services.device import DEVICE_ONLINE_SECONDS
from app.services.network import format_probe_node_name


MTR_DEADLINE_SECONDS = 20
STATUS_NAMES = {1: "queued", 2: "running", 3: "completed", 4: "partial_completed", 5: "failed"}


def list_mtr_devices(user_id: int) -> list[MTRDevice]:
    """查询当前用户在线且存在有效公开地址的节点。

    参数:
        user_id: 当前登录用户主键。
    返回:
        可创建双向 MTR 的节点名称与其地址列表。
    """
    now = int(time.time())
    with SessionLocal() as session:
        rows = session.execute(select(Device, IPDict).join(IPDict, IPDict.device_related_id == Device.id).where(Device.user_id == user_id, Device.device_id.is_not(None), Device.last_seen_at.is_not(None), Device.last_seen_at >= now - DEVICE_ONLINE_SECONDS, IPDict.public_status == 1).order_by(Device.id, IPDict.id)).all()
        devices: dict[int, MTRDevice] = {}
        for device, address in rows:
            try:
                parsed = ip_address(address.ip)
            except ValueError:
                continue
            if not parsed.is_global or parsed.version != address.ip_version:
                continue
            item = devices.setdefault(
                device.id,
                MTRDevice(
                    id=device.id,
                    nodeName=format_probe_node_name(address.province, address.isp),
                    ips=[],
                ),
            )
            item.ips.append(MTRDeviceIP(id=address.id, ip=parsed.compressed, ipVersion=parsed.version))
        return list(devices.values())


def create_mtr_task(user_id: int, source_device_id: int, source_ip_id: int, target_device_id: int, target_ip_id: int) -> CreateMTRData:
    """校验用户选择并创建两个关联的方向任务。

    参数:
        user_id: 当前登录用户主键。
        source_device_id: 设备 A 主键。
        source_ip_id: 设备 A 选择的 IP 主键。
        target_device_id: 设备 B 主键。
        target_ip_id: 设备 B 选择的 IP 主键。
    返回:
        新建主任务标识和初始状态。
    """
    if source_device_id == target_device_id:
        raise ValueError("请选择两个不同的在线设备")
    now = int(time.time())
    with SessionLocal.begin() as session:
        _, source_ip = _validate_endpoint(session, user_id, source_device_id, source_ip_id, now)
        _, target_ip = _validate_endpoint(session, user_id, target_device_id, target_ip_id, now)
        if source_ip.ip_version != target_ip.ip_version:
            raise ValueError("两个设备必须选择相同地址族的公网 IP")
        task = BidirectionalMTRTask(user_id=user_id, status=1, created_at=now)
        session.add(task)
        session.flush()
        _add_direction(session, task.id, "A_TO_B", source_ip, target_ip)
        _add_direction(session, task.id, "B_TO_A", target_ip, source_ip)
        return CreateMTRData(mtrTaskId=task.id, status="queued")


def claim_mtr_task(device_id: str) -> MTRAgentTask | None:
    """刷新设备心跳并以租约领取一个待执行方向任务。

    参数:
        device_id: Agent 本地设备标识。
    返回:
        当前设备可执行的 MTR 任务；没有任务时返回空。
    """
    now = int(time.time())
    with SessionLocal.begin() as session:
        device = session.scalar(select(Device).where(Device.device_id == device_id))
        if device is None:
            raise LookupError("设备不存在")
        device.last_seen_at = now
        _expire_mtr_tasks(session, now)
        direction = session.scalar(select(BidirectionalMTRDirection).join(BidirectionalMTRTask, BidirectionalMTRTask.id == BidirectionalMTRDirection.mtr_task_id).join(IPDict, IPDict.id == BidirectionalMTRDirection.source_ip_id).where(IPDict.device_related_id == device.id, BidirectionalMTRDirection.status == 1, BidirectionalMTRTask.status.in_((1, 2))).order_by(BidirectionalMTRDirection.id).with_for_update(skip_locked=True))
        if direction is None or not _is_direction_valid(session, direction, now):
            if direction is not None:
                direction.status, direction.error_code, direction.finished_at = 5, "ENDPOINT_EXPIRED", now
                _finalize_task(session, direction.mtr_task_id, now)
            return None
        source_ip = session.get(IPDict, direction.source_ip_id)
        target_ip = session.get(IPDict, direction.target_ip_id)
        if source_ip is None or target_ip is None:
            direction.status, direction.error_code, direction.finished_at = 5, "ENDPOINT_EXPIRED", now
            _finalize_task(session, direction.mtr_task_id, now)
            return None
        direction.status, direction.started_at, direction.lease_token = 2, now, secrets.token_hex(32)
        task = session.get(BidirectionalMTRTask, direction.mtr_task_id)
        if task is not None and task.status == 1:
            task.status, task.started_at = 2, now
        return MTRAgentTask(mtr_task_id=direction.mtr_task_id, direction=direction.direction, lease_token=direction.lease_token, source_ip=ip_address(source_ip.ip), target_ip=ip_address(target_ip.ip), ip_version=direction.ip_version)


def save_mtr_result(request: MTRResultRequest) -> None:
    """锁定主任务，校验租约和地址快照后幂等保存单方向结果。

    参数:
        request: Agent 上报的方向任务、租约、地址和逐跳结果。
    返回:
        无返回值；校验失败时抛出相应异常。
    """
    now = int(time.time())
    payload = [hop.model_dump() for hop in request.hops]
    with SessionLocal.begin() as session:
        task = session.scalar(select(BidirectionalMTRTask).where(BidirectionalMTRTask.id == request.mtr_task_id).with_for_update())
        if task is None:
            raise LookupError("双向 MTR 任务不存在")
        direction = session.scalar(select(BidirectionalMTRDirection).where(BidirectionalMTRDirection.mtr_task_id == request.mtr_task_id, BidirectionalMTRDirection.direction == request.direction).with_for_update())
        if direction is None:
            raise LookupError("MTR 方向任务不存在")
        if direction.status == 3 and direction.result_data == payload and direction.error_code == request.error_code:
            return
        if direction.status != 2 or direction.lease_token != request.lease_token:
            raise ValueError("MTR 方向任务租约无效或已结束")
        source_ip = session.get(IPDict, direction.source_ip_id)
        target_ip = session.get(IPDict, direction.target_ip_id)
        source_device = (
            session.get(Device, source_ip.device_related_id)
            if source_ip is not None
            else None
        )
        if source_device is None or target_ip is None or source_device.device_id != request.device_id or source_ip.ip != request.source_ip.compressed or target_ip.ip != request.target_ip.compressed or request.finished_at < request.started_at:
            raise PermissionError("MTR 结果与任务地址快照不匹配")
        direction.result_data = payload
        direction.error_code = request.error_code
        direction.status = 5 if request.error_code else 3
        direction.finished_at = now
        _finalize_task(session, direction.mtr_task_id, now)


def get_mtr_result(user_id: int, task_id: int) -> MTRTaskResult:
    """按用户权限查询双向 MTR 聚合状态和路径。

    参数:
        user_id: 当前登录用户主键。
        task_id: 双向 MTR 主任务主键。
    返回:
        两个方向分别保存的状态和逐跳结果。
    """
    now = int(time.time())
    with SessionLocal.begin() as session:
        task = session.get(BidirectionalMTRTask, task_id)
        if task is None:
            raise LookupError("双向 MTR 任务不存在")
        if task.user_id != user_id:
            raise PermissionError("无权查看该双向 MTR 任务")
        _expire_mtr_tasks(session, now)
        directions = session.scalars(select(BidirectionalMTRDirection).where(BidirectionalMTRDirection.mtr_task_id == task_id).order_by(BidirectionalMTRDirection.id)).all()
        result_directions = []
        for item in directions:
            source_ip = session.get(IPDict, item.source_ip_id)
            target_ip = session.get(IPDict, item.target_ip_id)
            if source_ip is None or target_ip is None:
                raise LookupError("MTR 方向任务的关联 IP 不存在")
            result_directions.append({"direction": item.direction, "sourceIp": source_ip.ip, "targetIp": target_ip.ip, "status": STATUS_NAMES[item.status], "errorCode": item.error_code, "hops": item.result_data or []})
        return MTRTaskResult(mtrTaskId=task.id, status=STATUS_NAMES[task.status], directions=result_directions)


def _validate_endpoint(session: Session, user_id: int, device_id: int, ip_id: int, now: int) -> tuple[Device, IPDict]:
    """校验用户设备、在线状态和所选公开公网地址。

    参数:
        session: 当前数据库事务会话。
        user_id: 当前登录用户主键。
        device_id: 所选设备主键。
        ip_id: 所选 IP 主键。
        now: 当前 Unix 秒级时间戳。
    返回:
        校验通过的设备和 IP 记录。
    """
    row = session.execute(select(Device, IPDict).join(IPDict, IPDict.device_related_id == Device.id).where(Device.id == device_id, Device.user_id == user_id, Device.device_id.is_not(None), Device.last_seen_at.is_not(None), Device.last_seen_at >= now - DEVICE_ONLINE_SECONDS, IPDict.id == ip_id, IPDict.public_status == 1)).first()
    if row is None:
        raise ValueError("设备或公网 IP 不可用、已离线或不属于当前用户")
    device, address = row
    try:
        parsed = ip_address(address.ip)
    except ValueError as exc:
        raise ValueError("所选公网 IP 无效") from exc
    if not parsed.is_global or parsed.version != address.ip_version:
        raise ValueError("所选地址不是有效公网 IP")
    return device, address


def _add_direction(session: Session, task_id: int, name: str, source_ip: IPDict, target_ip: IPDict) -> None:
    """为主任务创建引用端点 IP 的方向任务。

    参数:
        session: 当前数据库事务会话。
        task_id: 双向 MTR 主任务主键。
        name: 方向名称。
        source_ip: 发起探测的地址。
        target_ip: 接收探测的地址。
    返回:
        无返回值。
    """
    session.add(BidirectionalMTRDirection(mtr_task_id=task_id, direction=name, source_ip_id=source_ip.id, target_ip_id=target_ip.id, ip_version=source_ip.ip_version, status=1))


def _is_direction_valid(session: Session, direction: BidirectionalMTRDirection, now: int) -> bool:
    """确认领取前两个端点及其关联 IP 仍然有效。

    参数:
        session: 当前数据库事务会话。
        direction: 待领取的方向任务。
        now: 当前 Unix 秒级时间戳。
    返回:
        两端在线且关联 IP 仍为公开地址时返回 true。
    """
    for ip_id in (direction.source_ip_id, direction.target_ip_id):
        row = session.execute(select(Device, IPDict).join(IPDict, IPDict.device_related_id == Device.id).where(Device.device_id.is_not(None), Device.last_seen_at.is_not(None), Device.last_seen_at >= now - DEVICE_ONLINE_SECONDS, IPDict.id == ip_id, IPDict.public_status == 1)).first()
        if row is None:
            return False
    return True


def _expire_mtr_tasks(session: Session, now: int) -> None:
    """将超过截止时间的未完成方向任务标记为失败。

    参数:
        session: 当前数据库事务会话。
        now: 当前 Unix 秒级时间戳。
    返回:
        无返回值。
    """
    tasks = session.scalars(select(BidirectionalMTRTask).where(BidirectionalMTRTask.status.in_((1, 2)), BidirectionalMTRTask.created_at <= now - MTR_DEADLINE_SECONDS)).all()
    for task in tasks:
        directions = session.scalars(select(BidirectionalMTRDirection).where(BidirectionalMTRDirection.mtr_task_id == task.id, BidirectionalMTRDirection.status.in_((1, 2)))).all()
        for direction in directions:
            direction.status, direction.error_code, direction.finished_at = 5, "TIMEOUT", now
        _finalize_task(session, task.id, now)


def _finalize_task(session: Session, task_id: int, now: int) -> None:
    """在两个方向都结束后计算主任务的最终状态。

    参数:
        session: 当前数据库事务会话。
        task_id: 双向 MTR 主任务主键。
        now: 当前 Unix 秒级时间戳。
    返回:
        无返回值。
    """
    task = session.get(BidirectionalMTRTask, task_id)
    directions = session.scalars(select(BidirectionalMTRDirection).where(BidirectionalMTRDirection.mtr_task_id == task_id)).all()
    if task is None or any(item.status in (1, 2) for item in directions):
        return
    success_count = sum(item.status == 3 for item in directions)
    task.status = 3 if success_count == len(directions) else 4 if success_count else 5
    task.finished_at = now
