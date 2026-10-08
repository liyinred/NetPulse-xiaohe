"""持续探测目标发现、结果和告警持久化服务。"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from ipaddress import IPv4Address, IPv6Address, ip_address
from time import time
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Select, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.alert_event import AlertEvent
from app.models.probe_alert_state import ProbeAlertState
from app.models.device import Device
from app.models.ip_dict import IPDict
from app.models.probe_state import (
    ICMPProbeState,
    TCPProbeState,
    UDPProbeState,
)
from app.models.user import User
from app.schemas.probe import (
    ProbeNodeItem,
    ProbePeriodReportRow,
    ProbeProtocolSummary,
    ProbeRangeType,
    ProbeReportData,
    ProbeReportRow,
    ProbeResultRequest,
    ProbeTarget,
    ProbeTargetsRequest,
    ProbeTargetsResponse,
    ProbeTrendData,
    ProbeTrendSeries,
    ProtocolType,
)
from app.schemas.user import UserLevel
from app.services.device import DEVICE_ONLINE_SECONDS, _upsert_ip_record
from app.services.network import (
    ISP_NAMES,
    IPLookupError,
    NetworkInfo,
    PROVINCE_NAMES,
    format_probe_node_label,
    format_probe_node_name,
    lookup_network,
)
from app.services.wechat import TemplateMessage


logger = logging.getLogger(__name__)

PROBE_MODE_CODES = {"cross_isp": 1, "cross_province": 2}
PROTOCOL_CODES = {"icmp": 1, "tcp": 2, "udp": 3}
PROBE_MODE_NAMES = {"cross_isp": "异网", "cross_province": "跨省"}
ALERT_TIME_ZONE = ZoneInfo("Asia/Shanghai")
PROBE_RANGE_DAYS = {"1d": 1, "2d": 2, "7d": 7}
REPORT_LOSS_FAILURE_RATE = 100.0
REPORT_LATENCY_FAILURE_MS = 300.0
ALERT_LOSS_RATE_THRESHOLD = 100
ALERT_CONFIRM_WINDOWS = 2
ALERT_REMINDER_SECONDS = 15 * 60
ALERT_EVENT_NAMES = {
    "firing": "探测丢包故障确认",
    "reminder": "探测丢包故障持续提醒",
    "recovered": "探测丢包故障恢复",
}
PROBE_STATE_MODELS = {
    "icmp": ICMPProbeState,
    "tcp": TCPProbeState,
    "udp": UDPProbeState,
}


def _build_protocol_summary(
    loss_rate: float | None,
    rtt_ms: float | None,
) -> ProbeProtocolSummary | None:
    """将数据库聚合值转换为前端使用的协议摘要。

    参数:
        loss_rate: 数据库存储的千分比平均丢包率；无样本时为 None。
        rtt_ms: 排除超时后的平均延迟；无有效延迟时为 None。
    返回:
        换算为百分比并完成取整的协议摘要；无样本时返回 None。
    """
    if loss_rate is None:
        return None
    return ProbeProtocolSummary(
        lossRate=round(float(loss_rate) / 10, 1),
        averageLatencyMs=(
            round(float(rtt_ms), 1) if rtt_ms is not None else None
        ),
    )


def _get_user_probe_source_network(
    session: Session,
    user_id: int,
    user_level: int,
    source_ip_id: int,
) -> tuple[int | None, int | None]:
    """校验用户对探测源节点的访问权限并返回其网络属性。

    参数:
        session: 当前数据库会话。
        user_id: 当前登录用户的内部主键。
        user_level: 当前登录用户的等级。
        source_ip_id: 用户选择的源 IP 记录主键。
    返回:
        源节点的省份编码和运营商编码。
    """
    statement = (
        select(IPDict.province, IPDict.isp)
        .join(Device, IPDict.device_related_id == Device.id)
        .where(IPDict.id == source_ip_id)
    )
    if user_level < UserLevel.PREMIUM:
        statement = statement.where(Device.user_id == user_id)
    source_record = session.execute(statement).one_or_none()
    if source_record is None:
        raise ValueError("探测节点不存在或无权访问")
    return source_record.province, source_record.isp


def _exclude_report_full_loss(
    statement: Select,
    state_model: type[ICMPProbeState] | type[TCPProbeState] | type[UDPProbeState],
) -> Select:
    """排除 ICMP 全丢包及其关联样本，同时排除 TCP 自身的全丢包样本。

    参数:
        statement: 尚未执行的协议聚合查询。
        state_model: 当前查询使用的协议状态模型。
    返回:
        按分钟、源 IP、目标 IP 和探测模式排除 ICMP 全丢包的查询；
        TCP 自身全丢包的样本也排除；无对应 ICMP 记录的其他样本保留。
    """
    if state_model is ICMPProbeState:
        return statement.where(state_model.loss_rate < 1000)
    if state_model is TCPProbeState:
        statement = statement.where(state_model.loss_rate < 1000)
    failed_icmp = select(ICMPProbeState.time_id).where(
        ICMPProbeState.time_id == state_model.time_id,
        ICMPProbeState.source_ip_id == state_model.source_ip_id,
        ICMPProbeState.target_ip_id == state_model.target_ip_id,
        ICMPProbeState.probe_mode == state_model.probe_mode,
        ICMPProbeState.loss_rate == 1000,
    ).correlate(state_model).exists()
    return statement.where(~failed_icmp)


def _build_probe_report(
    session: Session,
    user_id: int,
    user_level: int,
    source_ip_id: int,
    source_province: int | None,
    source_isp: int | None,
    probe_mode: int,
    start_time: int,
    end_time: int,
    previous_day_date: str,
    previous_day_rows: list[ProbePeriodReportRow],
) -> ProbeReportData:
    """按探测分类汇总三协议结果，排除 ICMP 全丢包关联样本及 TCP 全丢包样本。

    参数:
        session: 当前数据库会话。
        user_id: 当前登录用户的内部主键。
        user_level: 当前登录用户的等级。
        source_ip_id: 用户选择的源 IP 记录主键。
        source_province: 源节点省份编码。
        source_isp: 源节点运营商编码。
        probe_mode: 探测模式编码，1 为异网，2 为跨省。
        start_time: 查询起始 Unix 时间戳。
        end_time: 查询结束 Unix 时间戳。
        previous_day_date: 北京时间前一天的日期。
        previous_day_rows: 前一天全天及晚高峰的平均结果。
    返回:
        统计起止时间、覆盖概况及三协议平均结果，延迟平均值排除 300ms 超时。
    """
    rows_by_network: dict[tuple[int | None, int | None], ProbeReportRow] = {}
    for protocol_type, state_model in PROBE_STATE_MODELS.items():
        statement = (
            select(
                IPDict.province,
                IPDict.isp,
                func.avg(state_model.loss_rate).label("loss_rate"),
                func.avg(
                    case(
                        (
                            state_model.rtt_ms < REPORT_LATENCY_FAILURE_MS,
                            state_model.rtt_ms,
                        )
                    )
                ).label("rtt_ms"),
            )
            .join(IPDict, IPDict.id == state_model.target_ip_id)
            .where(
                state_model.source_ip_id == source_ip_id,
                state_model.probe_mode == probe_mode,
                state_model.time_id.between(start_time, end_time),
            )
            .group_by(IPDict.province, IPDict.isp)
        )
        statement = _filter_probe_mode(
            statement, source_province, source_isp, probe_mode
        )
        statement = _exclude_report_full_loss(statement, state_model)
        if user_level < UserLevel.PREMIUM:
            statement = statement.where(
                state_model.device_related_id.in_(
                    select(Device.id).where(Device.user_id == user_id)
                )
            )
        records = session.execute(statement).all()
        for record in records:
            network_key = (record.province, record.isp)
            report_row = rows_by_network.setdefault(
                network_key,
                ProbeReportRow(
                    province=record.province,
                    provinceName=PROVINCE_NAMES.get(record.province, "未知"),
                    isp=record.isp,
                    ispName=ISP_NAMES.get(record.isp, "未知"),
                    isCrossIsp=(
                        source_isp is not None
                        and record.isp is not None
                        and record.isp != source_isp
                    ),
                    isCrossProvince=(
                        source_province is not None
                        and record.province is not None
                        and record.province != source_province
                    ),
                ),
            )
            setattr(
                report_row,
                protocol_type,
                _build_protocol_summary(record.loss_rate, record.rtt_ms),
            )

    rows = sorted(
        rows_by_network.values(),
        key=lambda row: (row.province or 0, row.isp or 0),
    )
    covered_provinces = _apply_probe_report_coverage(rows)
    return ProbeReportData(
        startTime=start_time,
        endTime=end_time,
        sourceProvinceName=PROVINCE_NAMES.get(source_province, "未知"),
        sourceIspName=ISP_NAMES.get(source_isp, "未知"),
        crossIspCovered=any(row.isCovered and row.isCrossIsp for row in rows),
        crossProvinceCovered=any(
            row.isCovered and row.isCrossProvince for row in rows
        ),
        coveredProvinces=covered_provinces,
        rows=rows,
        previousDayDate=previous_day_date,
        previousDayRows=previous_day_rows,
    )


def _build_previous_day_report(
    session: Session,
    user_id: int,
    user_level: int,
    source_ip_id: int,
    source_province: int | None,
    source_isp: int | None,
    probe_mode: int,
    current_time: int,
) -> tuple[str, list[ProbePeriodReportRow]]:
    """汇总昨日分时结果，排除 ICMP 全丢包关联样本及 TCP 全丢包样本。

    参数:
        session: 当前数据库会话。
        user_id: 当前登录用户的内部主键。
        user_level: 当前登录用户的等级。
        source_ip_id: 用户选择的源 IP 记录主键。
        source_province: 源节点省份编码。
        source_isp: 源节点运营商编码。
        probe_mode: 探测模式编码，1 为异网，2 为跨省。
        current_time: 用于确定前一天的 Unix 秒时间戳。
    返回:
        前一天日期及按目标网络分组的全天、晚高峰三协议平均结果。
    """
    previous_day_start = (
        datetime.fromtimestamp(current_time, ALERT_TIME_ZONE) - timedelta(days=1)
    ).replace(hour=0, minute=0, second=0, microsecond=0)
    full_day_start = int(previous_day_start.timestamp())
    full_day_end = int((previous_day_start + timedelta(days=1)).timestamp()) - 60
    peak_start = int(previous_day_start.replace(hour=20).timestamp())
    peak_end = int(previous_day_start.replace(hour=22).timestamp()) - 60
    rows: dict[
        tuple[int | None, int | None, str], ProbePeriodReportRow
    ] = {}

    for protocol_type, state_model in PROBE_STATE_MODELS.items():
        statement = select(
            IPDict.province,
            IPDict.isp,
            func.avg(state_model.loss_rate).label("full_day_loss_rate"),
            func.avg(
                case(
                    (
                        state_model.rtt_ms < REPORT_LATENCY_FAILURE_MS,
                        state_model.rtt_ms,
                    )
                )
            ).label("full_day_rtt_ms"),
            func.avg(
                case(
                    (
                        state_model.time_id.between(peak_start, peak_end),
                        state_model.loss_rate,
                    )
                )
            ).label("peak_loss_rate"),
            func.avg(
                case(
                    (
                        state_model.time_id.between(peak_start, peak_end),
                        case(
                            (
                                state_model.rtt_ms < REPORT_LATENCY_FAILURE_MS,
                                state_model.rtt_ms,
                            )
                        ),
                    )
                )
            ).label("peak_rtt_ms"),
        ).join(
            IPDict, IPDict.id == state_model.target_ip_id
        ).where(
            state_model.source_ip_id == source_ip_id,
            state_model.probe_mode == probe_mode,
            state_model.time_id.between(full_day_start, full_day_end),
        ).group_by(
            IPDict.province,
            IPDict.isp,
        )
        statement = _filter_probe_mode(
            statement, source_province, source_isp, probe_mode
        )
        statement = _exclude_report_full_loss(statement, state_model)
        if user_level < UserLevel.PREMIUM:
            statement = statement.where(
                state_model.device_related_id.in_(
                    select(Device.id).where(Device.user_id == user_id)
                )
            )
        for record in session.execute(statement).all():
            period_values = (
                (
                    "full_day",
                    record.full_day_loss_rate,
                    record.full_day_rtt_ms,
                ),
                ("evening_peak", record.peak_loss_rate, record.peak_rtt_ms),
            )
            for period, loss_rate, rtt_ms in period_values:
                row_key = (record.province, record.isp, period)
                row = rows.setdefault(
                    row_key,
                    ProbePeriodReportRow(
                        province=record.province,
                        provinceName=PROVINCE_NAMES.get(record.province, "未知"),
                        isp=record.isp,
                        ispName=ISP_NAMES.get(record.isp, "未知"),
                        period=period,
                    ),
                )
                setattr(
                    row,
                    protocol_type,
                    _build_protocol_summary(loss_rate, rtt_ms),
                )

    period_order = {"full_day": 0, "evening_peak": 1}
    sorted_rows = sorted(
        rows.values(),
        key=lambda row: (
            row.province or 0,
            row.isp or 0,
            period_order[row.period],
        ),
    )
    return previous_day_start.strftime("%Y-%m-%d"), sorted_rows


def _has_probe_report_failure(row: ProbeReportRow) -> bool:
    """判断报告分组是否包含达到失败阈值的协议指标。

    参数:
        row: 按目标省份和运营商聚合的报告分组。
    返回:
        任一协议的平均丢包或平均延迟达到失败阈值时返回 True。
    """
    summaries = (row.icmp, row.tcp, row.udp)
    return any(
        summary is not None
        and (
            summary.lossRate >= REPORT_LOSS_FAILURE_RATE
            or summary.averageLatencyMs is None
            or summary.averageLatencyMs >= REPORT_LATENCY_FAILURE_MS
        )
        for summary in summaries
    )


def _apply_probe_report_coverage(rows: list[ProbeReportRow]) -> list[str]:
    """按省份传播失败状态并返回仍然覆盖的省份名称。

    参数:
        rows: 已完成三协议聚合的报告分组。
    返回:
        未出现失败阈值且网络属性已知的去重省份名称。
    """
    uncovered_provinces = {
        row.province for row in rows if _has_probe_report_failure(row)
    }
    for row in rows:
        row.isCovered = row.province not in uncovered_provinces
    return list(
        dict.fromkeys(
            row.provinceName
            for row in rows
            if (
                row.isCovered
                and row.province is not None
                and row.provinceName != "未知"
            )
        )
    )


@dataclass
class _AlertTemplateGroup:
    """保存同一模板消息分组中的节点和最高丢包率。"""

    openid: str
    source_ip: str
    probe_type: str
    unix_timestamp: int
    event_kind: str = "firing"
    node_names: list[str] = field(default_factory=list)
    node_name_set: set[str] = field(default_factory=set)
    maximum_loss_rate: int = 0

    def add_alert(self, node_name: str, loss_rate: int) -> None:
        """向模板消息分组追加节点并更新最高丢包率。

        参数:
            node_name: 采用“省份运营商”格式的探测节点名称。
            loss_rate: 当前节点的整数千分比丢包率。
        返回:
            无返回值；相同节点名称仅保留一次。
        """
        if node_name not in self.node_name_set:
            self.node_name_set.add(node_name)
            self.node_names.append(node_name)
        self.maximum_loss_rate = max(self.maximum_loss_rate, loss_rate)


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
    """判断源目标是否符合异网不同运营商或跨省同运营商的探测分类。

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
        source.isp is not None
        and target.isp is not None
        and source.isp == target.isp
        and source.province not in (None, 1)
        and target.province not in (None, 1)
        and source.province != target.province
    )


def _filter_probe_mode(
    statement: Select,
    source_province: int | None,
    source_isp: int | None,
    probe_mode: int,
) -> Select:
    """为已关联目标 IPDict 的结果查询添加探测分类条件。

    参数:
        statement: 已关联目标 IPDict、尚未执行的结果查询。
        source_province: 源节点省份编码，1 表示未知省份。
        source_isp: 源节点运营商编码。
        probe_mode: 探测模式编码，1 为异网，2 为跨省。
    返回:
        异网仅保留不同运营商、跨省仅保留同运营商不同省份的查询。
    """
    if source_isp is None:
        return statement.where(False)
    if probe_mode == PROBE_MODE_CODES["cross_isp"]:
        return statement.where(IPDict.isp != source_isp)
    if source_province in (None, 1):
        return statement.where(False)
    return statement.where(
        IPDict.isp == source_isp,
        IPDict.province.not_in((1, source_province)),
    )


def _load_targets(
    rows: list[IPDict],
    source: IPDict,
    device_id: int,
    version: int,
    mode: str,
    online_device_ids: set[int],
) -> list[ProbeTarget]:
    """从已加载的公开 IP 中筛选指定分类的探测目标。

    参数:
        rows: 已按主键排序的公开候选 IP 记录。
        source: 当前设备的源 IP 记录。
        device_id: 当前 Agent 设备内部主键。
        version: 目标 IP 版本。
        mode: cross_isp 或 cross_province。
        online_device_ids: 当前在线的设备内部主键集合。
    返回:
        按 IP 记录主键排序且携带 TCP 回复模式和 UDP 可用状态的目标列表。
    """
    return [
        ProbeTarget(
            public_ip=ip_address(row.ip),
            isp=row.isp,
            province=row.province,
            tcp_responder_enabled=(
                device_id in online_device_ids
                and row.device_related_id in online_device_ids
            ),
            udp_enabled=row.device_related_id in online_device_ids,
        )
        for row in rows
        if row.id != source.id
        and row.device_related_id != device_id
        and row.isp is not None
        and row.province is not None
        and _is_valid_target_ip(row.ip, version)
        and _matches_mode(source, row, mode)
    ]


def _load_cached_network_info(
    public_ip: IPv4Address | IPv6Address,
) -> NetworkInfo | None:
    """从 ip_dict 读取可复用的 IP 归属信息。

    参数:
        public_ip: 要查询缓存的公网 IPv4 或 IPv6 地址。
    返回:
        IP 版本及归属字段有效时返回缓存信息，否则返回 None。
    """
    with SessionLocal() as session:
        record = session.scalar(select(IPDict).where(IPDict.ip == str(public_ip)))
        if (
            record is None
            or record.ip_version != public_ip.version
            or record.isp not in ISP_NAMES
            or record.province not in PROVINCE_NAMES
        ):
            return None
        return NetworkInfo(
            public_ip=public_ip,
            isp=record.isp,
            province=record.province,
            isp_name=ISP_NAMES[record.isp],
            province_name=PROVINCE_NAMES[record.province],
            city_name=record.city or "",
        )


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
    ipv4_network_info = _load_cached_network_info(request.source_ipv4)
    if ipv4_network_info is None:
        ipv4_network_info = await lookup_network(request.source_ipv4)
    ipv6_network_info = None
    if request.source_ipv6 is not None:
        ipv6_network_info = _load_cached_network_info(request.source_ipv6)
        if ipv6_network_info is None:
            try:
                ipv6_network_info = await lookup_network(request.source_ipv6)
            except IPLookupError as exc:
                logger.warning(
                    "IPv6 归属查询失败，本次仅返回 IPv4 探测目标: %s",
                    exc,
                )
    current_time = int(time())
    with SessionLocal.begin() as session:
        device = _get_device(session, request.device_id)
        device.last_seen_at = current_time
        source_ipv4 = _upsert_ip_record(
            session,
            device.id,
            request.source_ipv4,
            current_time,
            ipv4_network_info,
        )
        source_ipv6 = None
        if request.source_ipv6 is not None:
            source_ipv6 = _upsert_ip_record(
                session,
                device.id,
                request.source_ipv6,
                current_time,
                ipv6_network_info,
            )
        session.flush()
        device_id = device.id

    with SessionLocal() as session:
        versions = [4]
        if source_ipv6 is not None and ipv6_network_info is not None:
            versions.append(6)
        rows_by_version = {version: [] for version in versions}
        for row in session.scalars(
            select(IPDict)
            .where(
                IPDict.public_status == 1,
                IPDict.ip_version.in_(versions),
            )
            .order_by(IPDict.id)
        ):
            rows_by_version[row.ip_version].append(row)
        online_device_ids = set(
            session.scalars(
                select(Device.id).where(
                    Device.device_id.is_not(None),
                    Device.last_seen_at.is_not(None),
                    Device.last_seen_at >= current_time - DEVICE_ONLINE_SECONDS,
                )
            ).all()
        )
        response = ProbeTargetsResponse(
            source_ipv4=request.source_ipv4,
            source_ipv6=request.source_ipv6,
            cross_isp_ipv4_targets=_load_targets(
                rows_by_version[4],
                source_ipv4,
                device_id,
                4,
                "cross_isp",
                online_device_ids,
            ),
            cross_province_ipv4_targets=_load_targets(
                rows_by_version[4],
                source_ipv4,
                device_id,
                4,
                "cross_province",
                online_device_ids,
            ),
        )
        if source_ipv6 is not None:
            if ipv6_network_info is None:
                response.cross_isp_ipv6_targets = []
                response.cross_province_ipv6_targets = []
            else:
                response.cross_isp_ipv6_targets = _load_targets(
                    rows_by_version[6],
                    source_ipv6,
                    device_id,
                    6,
                    "cross_isp",
                    online_device_ids,
                )
                response.cross_province_ipv6_targets = _load_targets(
                    rows_by_version[6],
                    source_ipv6,
                    device_id,
                    6,
                    "cross_province",
                    online_device_ids,
                )
    target_lists = (
        response.cross_isp_ipv4_targets,
        response.cross_province_ipv4_targets,
        response.cross_isp_ipv6_targets,
        response.cross_province_ipv6_targets,
    )
    if not any(target_lists):
        raise ValueError("当前获取的异网和跨省探测目标为空")
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
    record = session.execute(
        select(Device, IPDict)
        .join(IPDict, IPDict.device_related_id == Device.id)
        .where(
            Device.device_id == device_id,
            Device.user_id.is_not(None),
            IPDict.ip == str(source_ip),
            IPDict.ip_version == ip_version,
        )
    ).one_or_none()
    if record is None:
        raise ValueError("设备未绑定或 source_ip 不属于当前设备")
    return record[0], record[1]


def _validate_probe_target(
    device: Device,
    source: IPDict,
    target: IPDict | None,
    mode: str,
) -> IPDict:
    """校验已加载目标的公开状态、设备归属和探测分类。

    参数:
        device: 当前 Agent 设备。
        source: 已校验的源 IP 记录。
        target: 待校验的目标 IP 记录，不存在时为 None。
        mode: 上报分类。
    返回:
        校验通过的目标 IP 记录。
    """
    if (
        target is None
        or target.public_status != 1
        or target.device_related_id == device.id
        or not _matches_mode(source, target, mode)
    ):
        raise ValueError("target_ip 不符合当前探测分类")
    return target


def _save_probe_result_once(request: ProbeResultRequest) -> list[TemplateMessage]:
    """在单个事务中保存分钟结果并更新跨分钟告警状态。

    参数:
        request: Agent 上报的完整分钟结果。
    返回:
        提交后待发送的通知；重复且内容一致的请求返回空列表。
    """
    mode_code = PROBE_MODE_CODES[request.probe_mode]
    with SessionLocal.begin() as session:
        # 先锁定设备，再读取结果和状态，串行化同设备的并发上报。
        session.execute(
            select(Device.id)
            .where(Device.device_id == request.device_id)
            .with_for_update()
        ).all()
        device, source = _get_owned_source(
            session,
            request.device_id,
            request.source_ip,
            request.ip_version,
        )
        target_ips = [str(result.target_ip) for result in request.targets]
        if any(
            result.target_ip.version != request.ip_version
            for result in request.targets
        ):
            raise ValueError("target_ip 与 ip_version 不匹配")
        targets_by_ip = {
            target.ip: target
            for target in session.scalars(
                select(IPDict).where(
                    IPDict.ip.in_(target_ips),
                    IPDict.ip_version == request.ip_version,
                    IPDict.public_status == 1,
                )
            ).all()
        }
        target_results = {}
        for target_result in request.targets:
            target = _validate_probe_target(
                device,
                source,
                targets_by_ip.get(str(target_result.target_ip)),
                request.probe_mode,
            )
            if target.id in target_results:
                raise ValueError("targets 包含重复 IP")
            target_results[target.id] = target_result

        protocol_states = []
        for field_name, state_model in PROBE_STATE_MODELS.items():
            existing_rows = session.scalars(
                select(state_model).where(
                    state_model.time_id == request.unix_timestamp,
                    state_model.source_ip_id == source.id,
                    state_model.probe_mode == mode_code,
                )
            ).all()
            existing_values = {
                row.target_ip_id: (
                    row.device_related_id,
                    row.loss_rate,
                    row.rtt_ms,
                )
                for row in existing_rows
            }
            incoming_values = {}
            for target_id, target_result in target_results.items():
                protocol_result = getattr(target_result, field_name)
                if protocol_result is None:
                    continue
                incoming_values[target_id] = (
                    device.id,
                    protocol_result.loss_rate,
                    protocol_result.average_latency_ms,
                )
            protocol_states.append(
                (state_model, incoming_values, existing_values)
            )

        if any(existing for _, _, existing in protocol_states):
            if any(
                incoming != existing
                for _, incoming, existing in protocol_states
            ):
                raise ValueError("相同幂等键的上报内容不一致")
            return []

        for state_model, incoming_values, _ in protocol_states:
            for target_id in sorted(incoming_values):
                (
                    device_related_id,
                    loss_rate,
                    rtt_ms,
                ) = incoming_values[target_id]
                session.add(
                    state_model(
                        time_id=request.unix_timestamp,
                        device_related_id=device_related_id,
                        source_ip_id=source.id,
                        target_ip_id=target_id,
                        probe_mode=mode_code,
                        loss_rate=loss_rate,
                        rtt_ms=rtt_ms,
                    )
                )
        messages = _update_probe_alert_states(
            session, request, device, source, targets_by_ip
        )
    return messages


def _is_duplicate_key_error(exc: IntegrityError) -> bool:
    """判断数据库完整性错误是否为 MySQL 重复键冲突。

    参数:
        exc: SQLAlchemy 抛出的数据库完整性错误。
    返回:
        底层 MySQL 错误码为 1062 时返回 True。
    """
    original_args = getattr(exc.orig, "args", ())
    return bool(original_args) and original_args[0] == 1062


def save_probe_result(request: ProbeResultRequest) -> list[TemplateMessage]:
    """幂等保存分钟探测结果，并对并发重复写入重试一次。

    参数:
        request: Agent 上报的完整分钟结果。
    返回:
        提交后待发送的通知；重复且内容一致的请求返回空列表。
    """
    for attempt in range(2):
        try:
            return _save_probe_result_once(request)
        except IntegrityError as exc:
            if attempt > 0 or not _is_duplicate_key_error(exc):
                raise

    raise RuntimeError("探测结果写入竞态恢复失败")


def list_user_probe_nodes(
    user_id: int,
    user_level: int,
) -> list[ProbeNodeItem]:
    """按用户等级从设备及关联 IP 记录查询探测源节点，不读取探测结果表。

    参数:
        user_id: 当前登录用户的内部主键。
        user_level: 当前登录用户的等级，高级等级以上可查看全部节点。
    返回:
        按 IP 版本和地址排序的设备节点列表，包含尚无探测结果的节点。
    """
    with SessionLocal() as session:
        statement = (
            select(IPDict.id, IPDict.ip, IPDict.province, IPDict.isp)
            .select_from(Device)
            .join(IPDict, IPDict.device_related_id == Device.id)
            .order_by(IPDict.ip_version, IPDict.ip)
        )
        if user_level < UserLevel.PREMIUM:
            statement = statement.where(Device.user_id == user_id)
        records = session.execute(statement).all()
    return [
        ProbeNodeItem(
            id=record.id,
            ip=record.ip,
            label=format_probe_node_label(
                record.province,
                record.isp,
                record.ip,
            ),
        )
        for record in records
    ]


def _resolve_probe_time_range(
    range_type: ProbeRangeType,
    month: str | None,
    current_time: int,
) -> tuple[int, int]:
    """将预设范围或北京时间月份转换为闭区间 Unix 分钟时间戳。

    参数:
        range_type: 最近 1、2、7 天或月份范围。
        month: 月份范围使用的 YYYY-MM 字符串。
        current_time: 当前 Unix 秒时间戳。
    返回:
        起止自然分钟时间戳组成的闭区间。
    """
    current_minute = current_time - current_time % 60
    if range_type != "month":
        return (
            current_minute - PROBE_RANGE_DAYS[range_type] * 86400 + 60,
            current_minute,
        )
    if month is None:
        raise ValueError("月份范围必须提供 month")
    try:
        month_start = datetime.strptime(month, "%Y-%m").replace(
            tzinfo=ALERT_TIME_ZONE
        )
    except ValueError as exc:
        raise ValueError("month 必须使用 YYYY-MM 格式") from exc

    current_month = datetime.fromtimestamp(
        current_time, ALERT_TIME_ZONE
    ).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start > current_month:
        raise ValueError("不能查询未来月份")
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(
        day=1
    )
    range_end = min(int(next_month.timestamp()) - 60, current_minute)
    return int(month_start.timestamp()), range_end


def get_user_probe_report(
    user_id: int,
    user_level: int,
    source_ip_id: int,
    probe_mode: int,
    range_type: ProbeRangeType,
    month: str | None = None,
    current_time: int | None = None,
) -> ProbeReportData:
    """查询用户节点在指定探测模式和时间范围内的概览报告。

    参数:
        user_id: 当前登录用户的内部主键。
        user_level: 当前登录用户的等级，高级等级以上可查询全部节点。
        source_ip_id: 用户选择的源 IP 记录主键。
        probe_mode: 探测模式编码，1 为异网，2 为跨省。
        range_type: 最近 1、2、7 天或月份范围。
        month: 月份范围使用的 YYYY-MM 字符串。
        current_time: 可选的当前时间戳，主要用于确定相对范围。
    返回:
        按省份、运营商聚合的三协议概览报告。
    """
    report_current_time = int(time()) if current_time is None else current_time
    start_time, end_time = _resolve_probe_time_range(
        range_type,
        month,
        report_current_time,
    )
    with SessionLocal() as session:
        source_province, source_isp = _get_user_probe_source_network(
            session,
            user_id,
            user_level,
            source_ip_id,
        )
        previous_day_date, previous_day_rows = _build_previous_day_report(
            session,
            user_id,
            user_level,
            source_ip_id,
            source_province,
            source_isp,
            probe_mode,
            report_current_time,
        )
        return _build_probe_report(
            session,
            user_id,
            user_level,
            source_ip_id,
            source_province,
            source_isp,
            probe_mode,
            start_time,
            end_time,
            previous_day_date,
            previous_day_rows,
        )


def get_user_probe_trend(
    user_id: int,
    user_level: int,
    source_ip_id: int,
    probe_mode: int,
    protocol_type: ProtocolType,
    range_type: ProbeRangeType,
    month: str | None = None,
    current_time: int | None = None,
) -> ProbeTrendData:
    """查询符合异网或同运营商跨省规则的目标在指定范围内的分钟趋势。

    参数:
        user_id: 当前登录用户的内部主键。
        user_level: 当前登录用户的等级，高级等级以上可查询全部节点。
        source_ip_id: 用户选择的源 IP 记录主键。
        probe_mode: 探测模式编码，1 为异网，2 为跨省。
        protocol_type: icmp、tcp 或 udp 协议类型。
        range_type: 最近 1、2、7 天或月份范围。
        month: 月份范围使用的 YYYY-MM 字符串。
        current_time: 可选的当前时间戳，主要用于确定相对范围。
    返回:
        查询范围及按目标 IP 分组的指定协议趋势。
    """
    start_time, end_time = _resolve_probe_time_range(
        range_type,
        month,
        int(time()) if current_time is None else current_time,
    )
    state_model = PROBE_STATE_MODELS[protocol_type]

    with SessionLocal() as session:
        source_province, source_isp = _get_user_probe_source_network(
            session,
            user_id,
            user_level,
            source_ip_id,
        )

        statement = (
            select(
                state_model.time_id,
                IPDict.id.label("target_ip_id"),
                IPDict.ip,
                IPDict.province,
                IPDict.isp,
                state_model.loss_rate,
                state_model.rtt_ms,
            )
            .join(IPDict, IPDict.id == state_model.target_ip_id)
            .where(
                state_model.source_ip_id == source_ip_id,
                state_model.probe_mode == probe_mode,
                state_model.time_id.between(start_time, end_time),
            )
            .order_by(IPDict.id, state_model.time_id)
        )
        statement = _filter_probe_mode(
            statement, source_province, source_isp, probe_mode
        )
        if user_level < UserLevel.PREMIUM:
            statement = statement.where(
                state_model.device_related_id.in_(
                    select(Device.id).where(Device.user_id == user_id)
                )
            )
        records = session.execute(statement).all()
    series_by_target: dict[int, ProbeTrendSeries] = {}
    for record in records:
        series = series_by_target.setdefault(
            record.target_ip_id,
            ProbeTrendSeries(
                targetIpId=record.target_ip_id,
                targetIp=record.ip,
                label=format_probe_node_label(
                    record.province,
                    record.isp,
                    record.ip,
                ),
                points=[],
            ),
        )
        series.points.append(
            (
                record.time_id,
                round(float(record.loss_rate) / 10, 1),
                round(float(record.rtt_ms), 1),
            )
        )
    return ProbeTrendData(
        startTime=start_time,
        endTime=end_time,
        series=list(series_by_target.values()),
    )


def _accepts_probe_mode(user: User, probe_mode: str) -> bool:
    """判断用户设置是否接收指定探测分类的告警。

    参数:
        user: 源设备关联的微信用户。
        probe_mode: cross_isp 或 cross_province。
    返回:
        用户仍关注且告警类型匹配时返回 True。
    """
    mode_code = PROBE_MODE_CODES[probe_mode]
    return (
        user.subscribe_status == 1
        and user.alert_type in (mode_code, 3)
    )


def _format_alert_start_time(unix_timestamp: int) -> str:
    """格式化自然分钟告警的北京时间开始时刻。

    参数:
        unix_timestamp: 自然分钟窗口结束 Unix 时间戳。
    返回:
        精确到分钟的北京时间窗口开始时刻。
    """
    window_end = datetime.fromtimestamp(unix_timestamp, ALERT_TIME_ZONE)
    window_start = window_end - timedelta(minutes=1)
    return f"{window_start:%Y-%m-%d %H:%M}"


def _build_template_messages(
    groups: dict[tuple[str, str, str, str, int, str], _AlertTemplateGroup],
) -> list[TemplateMessage]:
    """将告警分组转换为微信模板消息。

    参数:
        groups: 按用户、源 IP、分类、协议、时间窗口和事件类型聚合的通知。
    返回:
        可直接交给微信服务发送的模板消息列表。
    """
    messages = []
    for group in groups.values():
        messages.append(
            TemplateMessage(
                openid=group.openid,
                data={
                    "first": ALERT_EVENT_NAMES[group.event_kind],
                    "keyword1": group.source_ip,
                    "keyword2": ", ".join(group.node_names),
                    "keyword3": group.probe_type,
                    "keyword4": _format_alert_start_time(
                        group.unix_timestamp
                    ),
                    "remark": (
                        f"最高丢包率：{group.maximum_loss_rate / 10:.1f}%，"
                        + (
                            "已连续 2 分钟丢包率不超过 10%。"
                            if group.event_kind == "recovered"
                            else "请及时检查设备网络。"
                        )
                    ),
                },
            )
        )
    return messages


def _advance_probe_alert_state(
    state: ProbeAlertState, window_at: int, loss_rate: int
) -> str | None:
    """推进单个维度的告警状态，缺失窗口打断连续计数。

    参数:
        state: 当前持久化状态。
        window_at: 当前自然分钟窗口结束时间。
        loss_rate: 当前窗口的整数千分比丢包率。
    返回:
        首次故障、持续提醒或恢复的事件类型；无需通知时返回 None。
    """
    if window_at <= state.last_window_at:
        return None
    if window_at - state.last_window_at != 60:
        state.abnormal_count = 0
        state.normal_count = 0
    state.last_window_at = window_at
    if loss_rate > ALERT_LOSS_RATE_THRESHOLD:
        state.normal_count = 0
        if not state.is_firing and state.abnormal_count == 0:
            state.fault_started_at = window_at - 60
        state.abnormal_count = min(state.abnormal_count + 1, ALERT_CONFIRM_WINDOWS)
        if not state.is_firing:
            if state.abnormal_count < ALERT_CONFIRM_WINDOWS:
                return None
            state.is_firing = True
            return "firing"
        if (
            state.last_notified_at is None
            or window_at - state.last_notified_at >= ALERT_REMINDER_SECONDS
        ):
            return "reminder"
        return None
    state.abnormal_count = 0
    state.normal_count = min(state.normal_count + 1, ALERT_CONFIRM_WINDOWS)
    if state.is_firing and state.normal_count >= ALERT_CONFIRM_WINDOWS:
        state.is_firing = False
        state.fault_started_at = None
        return "recovered"
    if not state.is_firing:
        state.fault_started_at = None
    return None


def _update_probe_alert_states(
    session: Session,
    request: ProbeResultRequest,
    device: Device,
    source: IPDict,
    targets_by_ip: dict[str, IPDict],
) -> list[TemplateMessage]:
    """在已持有设备行锁的结果事务内更新状态并记录通知事件。

    参数:
        session: 当前事务会话，调用者已锁定设备。
        request: 已校验的分钟结果。
        device: 上报设备。
        source: 已校验的源 IP。
        targets_by_ip: 已加载的目标 IP 记录。
    返回:
        按事件类型分组、待事务提交后发送的微信通知。
    """
    mode_code = PROBE_MODE_CODES[request.probe_mode]
    states = {
        (state.target_ip_id, state.protocol_type): state
        for state in session.scalars(
            select(ProbeAlertState).where(
                ProbeAlertState.source_ip_id == source.id,
                ProbeAlertState.probe_mode == mode_code,
            ).with_for_update()
        ).all()
    }
    user = session.get(User, device.user_id)
    accepts = bool(user and user.openid and _accepts_probe_mode(user, request.probe_mode))
    groups = {}
    for target_result in request.targets:
        target = targets_by_ip[str(target_result.target_ip)]
        for protocol, protocol_code in PROTOCOL_CODES.items():
            result = getattr(target_result, protocol)
            if result is None:
                continue
            state = states.get((target.id, protocol_code))
            if state is None:
                state = ProbeAlertState(
                    source_ip_id=source.id,
                    target_ip_id=target.id,
                    probe_mode=mode_code,
                    protocol_type=protocol_code,
                    is_firing=False,
                    abnormal_count=0,
                    normal_count=0,
                    last_window_at=0,
                )
                session.add(state)
            event_kind = _advance_probe_alert_state(
                state, request.unix_timestamp, result.loss_rate
            )
            if event_kind is None:
                continue
            # 记录事件决策时间；微信发送仍在事务外执行。
            state.last_notified_at = request.unix_timestamp
            session.add(AlertEvent(
                event_id=str(uuid4()),
                device_related_id=device.id,
                source_ip_id=source.id,
                target_ip_id=target.id,
                protocol_type=protocol_code,
                probe_mode=mode_code,
                occurred_at=request.unix_timestamp,
                message=(
                    f"{ALERT_EVENT_NAMES[event_kind]}: {request.probe_mode} {protocol} "
                    f"{source.ip} -> {target.ip}，丢包率 {result.loss_rate / 10:.1f}%"
                ),
            ))
            if not accepts:
                continue
            group_key = (
                user.openid, source.ip, request.probe_mode, protocol,
                request.unix_timestamp, event_kind,
            )
            group = groups.setdefault(group_key, _AlertTemplateGroup(
                openid=user.openid,
                source_ip=source.ip,
                probe_type=f"{PROBE_MODE_NAMES[request.probe_mode]} {protocol.upper()}",
                unix_timestamp=request.unix_timestamp,
                event_kind=event_kind,
            ))
            group.add_alert(format_probe_node_name(target.province, target.isp), result.loss_rate)
    return _build_template_messages(groups)
