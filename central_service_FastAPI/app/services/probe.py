"""持续探测目标发现、结果和告警持久化服务。"""

from ipaddress import IPv4Address, IPv6Address, ip_address
from time import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import (
    PROBE_DEVICE_OFFLINE_SECONDS,
    PROBE_IP_MAX_AGE_SECONDS,
)
from app.db.session import SessionLocal
from app.models.alert_event import AlertEvent
from app.models.device import Device
from app.models.ip_dict import IPDict
from app.models.probe_state import (
    ICMPProbeState,
    TCPProbeState,
    UDPProbeState,
)
from app.schemas.probe import (
    ProbeAlertsRequest,
    ProbeResultRequest,
    ProbeTarget,
    ProbeTargetsRequest,
    ProbeTargetsResponse,
)
from app.services.device import _upsert_ip_record
from app.services.network import lookup_network


PROBE_MODE_CODES = {"cross_isp": 1, "cross_province": 2}
PROTOCOL_CODES = {"icmp": 1, "tcp": 2, "udp": 3}


def _validate_public_source(
    source_ip: IPv4Address | IPv6Address,
    expected_version: int,
) -> None:
    """校验源地址为指定版本的公网 IP。

    参数:
        source_ip: Agent 提交的当前源地址。
        expected_version: 期望的 IP 版本。
    返回:
        无返回值；地址无效时抛出 ValueError。
    """
    if source_ip.version != expected_version or not source_ip.is_global:
        raise ValueError(f"source_ipv{expected_version} 不是有效公网地址")


def _get_device(session: Session, device_id: str) -> Device:
    """查询已绑定设备。

    参数:
        session: 当前数据库会话。
        device_id: Agent 设备标识。
    返回:
        匹配的已绑定设备。
    """
    device = session.scalar(
        select(Device).where(
            Device.device_id == device_id,
            Device.user_id.is_not(None),
        )
    )
    if device is None:
        raise ValueError("设备未绑定")
    return device


def _is_valid_target_ip(ip_text: str, version: int) -> bool:
    """判断候选地址是否为指定版本的公网 IP。

    参数:
        ip_text: 数据库保存的 IP 文本。
        version: 期望的 IP 版本。
    返回:
        地址合法、版本匹配且可公网路由时返回 True。
    """
    try:
        candidate = ip_address(ip_text)
    except ValueError:
        return False
    return candidate.version == version and candidate.is_global


def _matches_mode(source: IPDict, target: IPDict, mode: str) -> bool:
    """判断源目标网络属性是否符合指定探测分类。

    参数:
        source: 源 IP 记录。
        target: 候选目标 IP 记录。
        mode: cross_isp 或 cross_province。
    返回:
        符合分类条件时返回 True。
    """
    if mode == "cross_isp":
        return (
            source.isp is not None
            and target.isp is not None
            and source.isp != target.isp
        )
    return (
        source.province not in (None, 1)
        and target.province not in (None, 1)
        and source.province != target.province
    )


def _load_targets(
    session: Session,
    source: IPDict,
    device: Device,
    version: int,
    mode: str,
    current_time: int,
) -> list[ProbeTarget]:
    """查询同版本、在线且符合分类条件的公开目标。

    参数:
        session: 当前数据库会话。
        source: 当前设备的源 IP 记录。
        device: 当前 Agent 设备。
        version: 目标 IP 版本。
        mode: cross_isp 或 cross_province。
        current_time: 当前 Unix 时间戳。
    返回:
        按设备和 IP 记录主键排序的目标列表。
    """
    rows = session.scalars(
        select(IPDict)
        .join(Device, IPDict.device_related_id == Device.id)
        .where(
            IPDict.device_related_id != device.id,
            IPDict.device_related_id.is_not(None),
            IPDict.public_status == 1,
            IPDict.ip_version == version,
            Device.user_id.is_not(None),
            IPDict.update_time >= current_time - PROBE_IP_MAX_AGE_SECONDS,
            Device.last_seen_at.is_not(None),
            Device.last_seen_at
            >= current_time - PROBE_DEVICE_OFFLINE_SECONDS,
        )
        .order_by(Device.id, IPDict.id)
    ).all()
    return [
        ProbeTarget(public_ip=ip_address(row.ip), isp=row.isp, province=row.province)
        for row in rows
        if row.isp is not None
        and row.province is not None
        and _is_valid_target_ip(row.ip, version)
        and _matches_mode(source, row, mode)
    ]


async def discover_probe_targets(
    request: ProbeTargetsRequest,
) -> ProbeTargetsResponse:
    """刷新设备源地址并返回异网和跨省双栈目标。

    参数:
        request: 设备标识及当前公网 IPv4/IPv6。
    返回:
        始终包含 IPv4 分类列表、按需包含 IPv6 分类列表的响应。
    """
    _validate_public_source(request.source_ipv4, 4)
    if request.source_ipv6 is not None:
        _validate_public_source(request.source_ipv6, 6)
    ipv4_network_info = await lookup_network(request.source_ipv4)
    ipv6_network_info = None
    if request.source_ipv6 is not None:
        ipv6_network_info = await lookup_network(request.source_ipv6)
    current_time = int(time())
    with SessionLocal.begin() as session:
        device = _get_device(session, request.device_id)
        device.last_seen_at = current_time
        device.updated_time = current_time
        _upsert_ip_record(
            session,
            device.id,
            request.source_ipv4,
            current_time,
            ipv4_network_info,
        )
        if request.source_ipv6 is not None:
            _upsert_ip_record(
                session,
                device.id,
                request.source_ipv6,
                current_time,
                ipv6_network_info,
            )
        session.flush()
        source_ipv4 = session.scalar(
            select(IPDict).where(IPDict.ip == str(request.source_ipv4))
        )
        if source_ipv4 is None:
            raise RuntimeError("IPv4 源地址刷新失败")
        response = ProbeTargetsResponse(
            source_ipv4=request.source_ipv4,
            source_ipv6=request.source_ipv6,
            cross_isp_ipv4_targets=_load_targets(
                session, source_ipv4, device, 4, "cross_isp", current_time
            ),
            cross_province_ipv4_targets=_load_targets(
                session,
                source_ipv4,
                device,
                4,
                "cross_province",
                current_time,
            ),
        )
        if request.source_ipv6 is not None:
            source_ipv6 = session.scalar(
                select(IPDict).where(IPDict.ip == str(request.source_ipv6))
            )
            if source_ipv6 is None:
                raise RuntimeError("IPv6 源地址刷新失败")
            response.cross_isp_ipv6_targets = _load_targets(
                session, source_ipv6, device, 6, "cross_isp", current_time
            )
            response.cross_province_ipv6_targets = _load_targets(
                session,
                source_ipv6,
                device,
                6,
                "cross_province",
                current_time,
            )
        return response


def _get_owned_source(
    session: Session,
    device_id: str,
    source_ip: IPv4Address | IPv6Address,
    ip_version: int,
) -> tuple[Device, IPDict]:
    """校验源地址版本及设备归属。

    参数:
        session: 当前数据库会话。
        device_id: Agent 设备标识。
        source_ip: 上报使用的源地址。
        ip_version: 上报声明的 IP 版本。
    返回:
        已绑定设备及其源 IP 记录。
    """
    if source_ip.version != ip_version:
        raise ValueError("source_ip 与 ip_version 不匹配")
    device = _get_device(session, device_id)
    source = session.scalar(
        select(IPDict).where(
            IPDict.ip == str(source_ip),
            IPDict.ip_version == ip_version,
            IPDict.device_related_id == device.id,
        )
    )
    if source is None:
        raise ValueError("source_ip 不属于当前设备")
    return device, source


def _get_valid_target(
    session: Session,
    device: Device,
    source: IPDict,
    target_ip: IPv4Address | IPv6Address,
    ip_version: int,
    mode: str,
) -> IPDict:
    """校验上报目标的版本、设备归属、公开状态及分类。

    参数:
        session: 当前数据库会话。
        device: 当前 Agent 设备。
        source: 已校验的源 IP 记录。
        target_ip: 上报的目标地址。
        ip_version: 上报声明的 IP 版本。
        mode: 上报分类。
    返回:
        校验通过的目标 IP 记录。
    """
    if target_ip.version != ip_version:
        raise ValueError("target_ip 与 ip_version 不匹配")
    target = session.scalar(
        select(IPDict).where(
            IPDict.ip == str(target_ip),
            IPDict.ip_version == ip_version,
            IPDict.device_related_id.is_not(None),
            IPDict.device_related_id != device.id,
            IPDict.public_status == 1,
        )
    )
    if target is None or not _matches_mode(source, target, mode):
        raise ValueError("target_ip 不符合当前探测分类")
    return target


def save_probe_result(request: ProbeResultRequest) -> None:
    """校验并幂等保存一个分类的分钟探测结果。

    参数:
        request: Agent 上报的完整分钟结果。
    返回:
        无返回值；重复且内容一致的请求视为成功。
    """
    mode_code = PROBE_MODE_CODES[request.probe_mode]
    with SessionLocal.begin() as session:
        device, source = _get_owned_source(
            session,
            request.device_id,
            request.source_ip,
            request.ip_version,
        )
        target_results = {}
        for target_result in request.targets:
            target = _get_valid_target(
                session,
                device,
                source,
                target_result.target_ip,
                request.ip_version,
                request.probe_mode,
            )
            if target.id in target_results:
                raise ValueError("targets 包含重复 IP")
            target_results[target.id] = target_result

        state_models = (
            ("icmp", ICMPProbeState),
            ("tcp", TCPProbeState),
            ("udp", UDPProbeState),
        )
        protocol_states = []
        for field_name, state_model in state_models:
            existing_rows = session.scalars(
                select(state_model).where(
                    state_model.time_id == request.unix_timestamp,
                    state_model.source_ip_id == source.id,
                    state_model.probe_mode == mode_code,
                )
            ).all()
            existing_values = {
                row.target_ip_id: (row.loss_rate, row.rtt_ms)
                for row in existing_rows
            }
            incoming_values = {
                target_id: (
                    getattr(target_result, field_name).loss_rate,
                    getattr(target_result, field_name).average_latency_ms,
                )
                for target_id, target_result in target_results.items()
            }
            protocol_states.append(
                (state_model, incoming_values, existing_values)
            )

        if any(existing for _, _, existing in protocol_states):
            if any(
                incoming != existing
                for _, incoming, existing in protocol_states
            ):
                raise ValueError("相同幂等键的上报内容不一致")
            return

        for state_model, incoming_values, _ in protocol_states:
            for target_id, (loss_rate, rtt_ms) in incoming_values.items():
                session.add(
                    state_model(
                        time_id=request.unix_timestamp,
                        source_ip_id=source.id,
                        target_ip_id=target_id,
                        probe_mode=mode_code,
                        loss_rate=loss_rate,
                        rtt_ms=rtt_ms,
                    )
                )


def save_probe_alerts(request: ProbeAlertsRequest) -> None:
    """校验并幂等保存自然分钟聚合丢包告警。

    参数:
        request: Agent 上报的自然分钟聚合丢包告警。
    返回:
        无返回值；批次中已存在的 event_id 视为成功。
    """
    with SessionLocal.begin() as session:
        for alert in request.alerts:
            if session.get(AlertEvent, alert.event_id) is not None:
                continue
            device, source = _get_owned_source(
                session,
                alert.device_id,
                alert.source_ip,
                alert.ip_version,
            )
            target = _get_valid_target(
                session,
                device,
                source,
                alert.target_ip,
                alert.ip_version,
                alert.probe_mode,
            )
            message = (
                f"{alert.probe_mode} {alert.protocol_type} 分钟丢包: "
                f"{alert.source_ip} -> {alert.target_ip}"
            )
            session.add(
                AlertEvent(
                    event_id=alert.event_id,
                    source_ip_id=source.id,
                    target_ip_id=target.id,
                    protocol_type=PROTOCOL_CODES[alert.protocol_type],
                    probe_mode=PROBE_MODE_CODES[alert.probe_mode],
                    occurred_at=alert.unix_timestamp,
                    message=message,
                )
            )
