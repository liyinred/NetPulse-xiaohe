"""临时 IP 按需探测编排服务。"""

from hashlib import sha256
from ipaddress import IPv4Address, IPv6Address, ip_address
import time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.device import Device
from app.models.ip_dict import IPDict
from app.models.on_demand_probe import OnDemandExecution, OnDemandNodeTask, ProbeQuery
from app.schemas.on_demand_probe import (
    CreateProbeQueryData,
    OnDemandResultRequest,
    OnDemandTaskData,
    ProbeQueryResultData,
)
from app.services.device import DEVICE_ONLINE_SECONDS
from app.services.network import NetworkInfo, lookup_network


EXECUTION_DEADLINE_SECONDS = 15
QUERY_RETENTION_SECONDS = 24 * 60 * 60

EXECUTION_STATUS_NAMES = {
    1: "queued",
    2: "running",
    3: "completed",
    4: "partial_completed",
    5: "failed",
}


async def create_probe_query(
    user_id: int,
    target_ip: IPv4Address | IPv6Address,
) -> CreateProbeQueryData:
    """创建用户查询并复用相同目标的活动执行。

    参数:
        user_id: 发起查询的当前用户主键。
        target_ip: 已由请求模型解析的目标地址。
    返回:
        用户查询、共享执行及初始状态标识。
    """
    if not target_ip.is_global:
        raise ValueError("请输入可公开路由的公网 IP")
    canonical_ip = target_ip.compressed
    network_info = await lookup_network(target_ip)
    current_time = int(time.time())
    active_key = sha256(canonical_ip.encode("ascii")).hexdigest()

    for attempt in range(2):
        try:
            with SessionLocal.begin() as session:
                execution = session.scalar(
                    select(OnDemandExecution).where(
                        OnDemandExecution.active_key == active_key,
                        OnDemandExecution.status.in_((1, 2)),
                    )
                )
                if execution is not None:
                    _expire_execution(session, execution, current_time)
                if execution is None or execution.status not in (1, 2):
                    execution = _create_execution(
                        session,
                        network_info,
                        active_key,
                        current_time,
                    )
                query = ProbeQuery(
                    user_id=user_id,
                    execution_id=execution.id,
                    created_at=current_time,
                    expires_at=current_time + QUERY_RETENTION_SECONDS,
                )
                session.add(query)
                session.flush()
                return CreateProbeQueryData(
                    queryId=query.id,
                    executionId=execution.id,
                    status=EXECUTION_STATUS_NAMES[execution.status],
                    targetIp=execution.target_ip,
                )
        except IntegrityError as exc:
            if attempt > 0 or not _is_active_key_conflict(exc, active_key):
                raise

    raise RuntimeError("活动执行竞态恢复失败")


def _is_active_key_conflict(exc: IntegrityError, active_key: str) -> bool:
    """判断数据库错误是否由活动执行去重键冲突引起。

    参数:
        exc: SQLAlchemy 抛出的数据库完整性错误。
        active_key: 当前目标对应的活动执行去重键。
    返回:
        错误为 MySQL active_key 重复键冲突时返回 True。
    """
    original_args = getattr(exc.orig, "args", ())
    return (
        bool(original_args)
        and original_args[0] == 1062
        and active_key in str(exc.orig)
        and "active_key" in str(exc.orig)
    )


def _create_execution(
    session: Session,
    network_info: NetworkInfo,
    active_key: str,
    current_time: int,
) -> OnDemandExecution:
    """创建执行记录并为符合条件的在线设备生成唯一节点任务。

    参数:
        session: 当前数据库事务会话。
        network_info: 临时目标 IP 的归属信息。
        active_key: 活动执行去重键。
        current_time: 当前 Unix 秒级时间戳。
    返回:
        已写入并分配节点任务的执行记录。
    """
    execution = OnDemandExecution(
        target_ip=network_info.public_ip.compressed,
        ip_version=network_info.public_ip.version,
        target_isp=network_info.isp,
        target_province=network_info.province,
        active_key=active_key,
        status=1,
        created_at=current_time,
    )
    session.add(execution)
    session.flush()

    target_device_id = session.scalar(
        select(IPDict.device_related_id).where(IPDict.ip == execution.target_ip)
    )
    candidates = session.execute(
        select(Device, IPDict)
        .join(IPDict, IPDict.device_related_id == Device.id)
        .where(
            Device.device_id.is_not(None),
            Device.on_demand_status == 1,
            Device.last_seen_at.is_not(None),
            Device.last_seen_at >= current_time - DEVICE_ONLINE_SECONDS,
            IPDict.ip_version == execution.ip_version,
            IPDict.public_status == 1,
        )
        .order_by(Device.id, IPDict.update_time.desc(), IPDict.id.desc())
    ).all()
    selected_devices: set[int] = set()
    for device, source_ip in candidates:
        if device.id in selected_devices or device.id == target_device_id:
            continue
        selected_devices.add(device.id)
        try:
            source_address = ip_address(source_ip.ip)
        except ValueError:
            continue
        if source_address.version != execution.ip_version or not source_address.is_global:
            continue
        probe_modes = 0
        if source_ip.isp is not None and source_ip.isp != execution.target_isp:
            probe_modes |= 1
        if (
            source_ip.province not in (None, 1)
            and execution.target_province not in (None, 1)
            and source_ip.province != execution.target_province
        ):
            probe_modes |= 2
        if probe_modes == 0:
            continue
        session.add(
            OnDemandNodeTask(
                execution_id=execution.id,
                probe_device_id=device.id,
                source_ip_id=source_ip.id,
                probe_modes=probe_modes,
                status=1,
            )
        )
    session.flush()
    task_count = session.scalar(
        select(OnDemandNodeTask.id)
        .where(OnDemandNodeTask.execution_id == execution.id)
        .limit(1)
    )
    if task_count is None:
        execution.status = 5
        execution.active_key = None
        execution.finished_at = current_time
    return execution


def claim_on_demand_task(device_id: str) -> OnDemandTaskData | None:
    """刷新设备心跳并领取携带目标 TCP 回复模式和 UDP 在线能力的按需任务。

    参数:
        device_id: Agent 本地设备标识。
    返回:
        成功领取的固定参数任务；无任务或设备禁用时返回空。
    """
    current_time = int(time.time())
    with SessionLocal.begin() as session:
        device = session.scalar(
            select(Device).where(Device.device_id == device_id)
        )
        if device is None:
            raise LookupError("设备不存在")
        device.last_seen_at = current_time
        _expire_active_executions(session, current_time)
        if device.on_demand_status != 1:
            return None
        candidates = session.execute(
            select(OnDemandNodeTask.id, OnDemandNodeTask.execution_id)
            .join(OnDemandExecution, OnDemandExecution.id == OnDemandNodeTask.execution_id)
            .where(
                OnDemandNodeTask.probe_device_id == device.id,
                OnDemandNodeTask.status == 1,
                OnDemandExecution.status.in_((1, 2)),
            )
            .order_by(OnDemandNodeTask.id)
        ).all()
        for task_id, execution_id in candidates:
            execution, task = _lock_execution_and_task(
                session,
                execution_id,
                task_id,
            )
            if (
                execution is None
                or task is None
                or task.probe_device_id != device.id
                or task.status != 1
                or execution.status not in (1, 2)
            ):
                continue
            source_ip = session.get(IPDict, task.source_ip_id)
            if source_ip is None:
                raise LookupError("按需探测任务源 IP 不存在")
            target_device = session.scalar(
                select(Device)
                .join(IPDict, IPDict.device_related_id == Device.id)
                .where(IPDict.ip == execution.target_ip)
            )
            udp_enabled = (
                target_device is not None
                and target_device.device_id is not None
                and target_device.last_seen_at is not None
                and target_device.last_seen_at
                >= current_time - DEVICE_ONLINE_SECONDS
            )
            task.status = 2
            task.started_at = current_time
            if execution.status == 1:
                execution.status = 2
                execution.started_at = current_time
            return OnDemandTaskData(
                id=task.id,
                source_ip=ip_address(source_ip.ip),
                target_ip=ip_address(execution.target_ip),
                ip_version=execution.ip_version,
                tcp_responder_enabled=udp_enabled,
                udp_enabled=udp_enabled,
            )
        return None


def save_on_demand_result(request: OnDemandResultRequest) -> None:
    """校验并幂等保存 Agent 返回的完整三协议结果。

    参数:
        request: 节点任务、设备、源目标地址和三协议结果。
    返回:
        无返回值；任务不匹配、过期或幂等内容冲突时抛出异常。
    """
    current_time = int(time.time())
    result_data = request.results.model_dump(mode="json")
    with SessionLocal.begin() as session:
        execution_id = session.scalar(
            select(OnDemandNodeTask.execution_id).where(
                OnDemandNodeTask.id == request.task_id
            )
        )
        if execution_id is None:
            raise LookupError("按需探测任务不存在")
        execution, task = _lock_execution_and_task(
            session,
            execution_id,
            request.task_id,
        )
        if execution is None or task is None:
            raise LookupError("按需探测任务不存在")
        device = session.get(Device, task.probe_device_id)
        source_ip = session.get(IPDict, task.source_ip_id)
        if device is None or source_ip is None:
            raise LookupError("按需探测任务关联记录不存在")
        if task.status == 3:
            if task.result_data == result_data:
                return
            raise ValueError("相同任务已上报不同结果")
        _expire_execution(session, execution, current_time)
        if task.status != 2 or execution.status not in (1, 2):
            raise ValueError("按需探测任务不处于可上报状态")
        if device.device_id != request.device_id:
            raise PermissionError("按需探测任务不属于当前设备")
        if source_ip.device_related_id != device.id or source_ip.ip != request.source_ip.compressed:
            raise ValueError("任务源 IP 与设备当前记录不匹配")
        if execution.target_ip != request.target_ip.compressed:
            raise ValueError("任务目标 IP 不匹配")
        if request.source_ip.version != execution.ip_version or request.target_ip.version != execution.ip_version:
            raise ValueError("任务源目标 IP 版本不匹配")
        if request.finished_at < request.started_at:
            raise ValueError("任务完成时间不能早于开始时间")
        task.result_data = result_data
        task.status = 3
        task.finished_at = current_time
        _finalize_execution(session, execution, current_time)


def _lock_execution_and_task(
    session: Session,
    execution_id: int,
    task_id: int,
) -> tuple[OnDemandExecution | None, OnDemandNodeTask | None]:
    """按固定顺序锁定按需执行和单个节点任务。

    参数:
        session: 当前数据库事务会话。
        execution_id: 按需执行记录主键。
        task_id: 节点任务记录主键。
    返回:
        依次加锁后的执行和任务；记录不存在时对应项为空。
    """
    execution = session.scalar(
        select(OnDemandExecution)
        .where(OnDemandExecution.id == execution_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if execution is None:
        return None, None
    task = session.scalar(
        select(OnDemandNodeTask)
        .where(
            OnDemandNodeTask.id == task_id,
            OnDemandNodeTask.execution_id == execution_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return execution, task


def get_probe_query_result(user_id: int, query_id: int) -> ProbeQueryResultData:
    """按用户权限查询临时 IP 执行进度和已完成节点结果。

    参数:
        user_id: 当前登录用户主键。
        query_id: 用户查询记录主键。
    返回:
        执行状态、节点数量和两个分类的已完成结果。
    """
    current_time = int(time.time())
    with SessionLocal.begin() as session:
        row = session.execute(
            select(ProbeQuery, OnDemandExecution)
            .join(OnDemandExecution, OnDemandExecution.id == ProbeQuery.execution_id)
            .where(ProbeQuery.id == query_id)
        ).first()
        if row is None:
            raise LookupError("临时 IP 查询不存在")
        query, execution = row
        if query.user_id != user_id:
            raise PermissionError("无权查看该临时 IP 查询")
        if query.expires_at < current_time:
            raise PermissionError("临时 IP 查询结果已过期")
        _expire_execution(session, execution, current_time)
        task_rows = session.execute(
            select(OnDemandNodeTask, IPDict)
            .join(IPDict, IPDict.id == OnDemandNodeTask.source_ip_id)
            .where(OnDemandNodeTask.execution_id == execution.id)
            .order_by(OnDemandNodeTask.id)
        ).all()
        counts = {status: 0 for status in range(1, 6)}
        cross_isp_results: list[dict[str, object]] = []
        cross_province_results: list[dict[str, object]] = []
        for task, source_ip in task_rows:
            counts[task.status] += 1
            if task.status != 3 or task.result_data is None:
                continue
            item = {
                "sourceIpId": source_ip.id,
                "isp": source_ip.isp,
                "province": source_ip.province,
                **task.result_data,
            }
            if task.probe_modes & 1:
                cross_isp_results.append(item)
            if task.probe_modes & 2:
                cross_province_results.append(item)
        return ProbeQueryResultData(
            executionId=execution.id,
            status=EXECUTION_STATUS_NAMES[execution.status],
            targetIp=execution.target_ip,
            ipVersion=execution.ip_version,
            targetIsp=execution.target_isp,
            targetProvince=execution.target_province,
            totalNodeCount=len(task_rows),
            pendingNodeCount=counts[1],
            runningNodeCount=counts[2],
            completedNodeCount=counts[3],
            timeoutNodeCount=counts[4],
            failedNodeCount=counts[5],
            results={
                "crossIspResults": cross_isp_results,
                "crossProvinceResults": cross_province_results,
            },
        )


def _expire_active_executions(session: Session, current_time: int) -> None:
    """将超过总截止时间的活动执行批量推进到终态。

    参数:
        session: 当前数据库事务会话。
        current_time: 当前 Unix 秒级时间戳。
    返回:
        无返回值。
    """
    executions = session.scalars(
        select(OnDemandExecution).where(
            OnDemandExecution.status.in_((1, 2)),
            OnDemandExecution.created_at <= current_time - EXECUTION_DEADLINE_SECONDS,
        )
    ).all()
    for execution in executions:
        _expire_execution(session, execution, current_time)


def _expire_execution(
    session: Session,
    execution: OnDemandExecution,
    current_time: int,
) -> None:
    """在执行超过十五秒截止时间时标记未完成任务并计算终态。

    参数:
        session: 当前数据库事务会话。
        execution: 待检查的共享执行记录。
        current_time: 当前 Unix 秒级时间戳。
    返回:
        无返回值。
    """
    if (
        execution.status not in (1, 2)
        or current_time < execution.created_at + EXECUTION_DEADLINE_SECONDS
    ):
        return
    execution = session.scalar(
        select(OnDemandExecution)
        .where(OnDemandExecution.id == execution.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        execution is None
        or execution.status not in (1, 2)
        or current_time < execution.created_at + EXECUTION_DEADLINE_SECONDS
    ):
        return
    tasks = session.scalars(
        select(OnDemandNodeTask)
        .where(OnDemandNodeTask.execution_id == execution.id)
        .order_by(OnDemandNodeTask.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    for task in tasks:
        if task.status in (1, 2):
            task.status = 4
            task.finished_at = current_time
    _finalize_execution(session, execution, current_time, tasks)


def _finalize_execution(
    session: Session,
    execution: OnDemandExecution,
    current_time: int,
    tasks: list[OnDemandNodeTask] | None = None,
) -> None:
    """在全部节点进入终态后更新共享执行的最终状态。

    参数:
        session: 当前数据库事务会话。
        execution: 待更新的共享执行记录。
        current_time: 当前 Unix 秒级时间戳。
        tasks: 可复用的节点任务列表，未提供时从数据库查询。
    返回:
        无返回值。
    """
    if tasks is None:
        tasks = list(
            session.scalars(
                select(OnDemandNodeTask).where(OnDemandNodeTask.execution_id == execution.id)
            ).all()
        )
    if any(task.status in (1, 2) for task in tasks):
        return
    completed_count = sum(task.status == 3 for task in tasks)
    if tasks and completed_count == len(tasks):
        execution.status = 3
    elif completed_count > 0:
        execution.status = 4
    else:
        execution.status = 5
    execution.active_key = None
    execution.finished_at = current_time
