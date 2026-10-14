"""持续探测 API 数据模型。"""

from ipaddress import IPv4Address, IPv6Address
from typing import Literal

from pydantic import BaseModel, Field


ProbeMode = Literal["cross_isp", "cross_province"]
ProtocolType = Literal["icmp", "tcp", "udp"]
ProbeRangeType = Literal["1d", "2d", "7d", "month"]


class ProbeTarget(BaseModel):
    """保存中央服务下发的单个公开探测目标。"""

    public_ip: IPv4Address | IPv6Address
    isp: int
    province: int
    tcp_responder_enabled: bool = False
    udp_enabled: bool = False


class ProbeTargetsRequest(BaseModel):
    """定义 Agent 查询持续探测目标时提交的源地址。"""

    device_id: str = Field(min_length=1, max_length=64)
    source_ipv4: IPv4Address
    source_ipv6: IPv6Address | None = None


class ProbeTargetsResponse(BaseModel):
    """按分类和 IP 版本返回持续探测目标。"""

    source_ipv4: IPv4Address
    source_ipv6: IPv6Address | None = None
    cross_isp_ipv4_targets: list[ProbeTarget]
    cross_province_ipv4_targets: list[ProbeTarget]
    cross_isp_ipv6_targets: list[ProbeTarget] | None = None
    cross_province_ipv6_targets: list[ProbeTarget] | None = None


class ProtocolProbeResult(BaseModel):
    """保存一种协议在自然分钟窗口内的汇总结果。"""

    loss_rate: int = Field(ge=0, le=1000)
    average_latency_ms: int = Field(ge=0, le=300)


class TargetProbeResult(BaseModel):
    """保存一个目标的 ICMP、TCP 及可选 UDP 汇总结果。"""

    target_ip: IPv4Address | IPv6Address
    icmp: ProtocolProbeResult
    tcp: ProtocolProbeResult
    udp: ProtocolProbeResult | None = None


class ProbeResultRequest(BaseModel):
    """定义一个分类和源地址的分钟探测结果上报。"""

    device_id: str = Field(min_length=1, max_length=64)
    probe_mode: ProbeMode
    ip_version: Literal[4, 6]
    source_ip: IPv4Address | IPv6Address
    unix_timestamp: int = Field(gt=0)
    targets: list[TargetProbeResult] = Field(min_length=1)


class ProbeAlertRequest(BaseModel):
    """定义一个目标和协议的分钟丢包告警。"""

    event_id: str = Field(min_length=36, max_length=36)
    device_id: str = Field(min_length=1, max_length=64)
    probe_mode: ProbeMode
    ip_version: Literal[4, 6]
    source_ip: IPv4Address | IPv6Address
    target_ip: IPv4Address | IPv6Address
    protocol_type: ProtocolType
    loss_rate: int = Field(ge=1, le=1000)
    unix_timestamp: int = Field(gt=0)


class ProbeAlertsRequest(BaseModel):
    """定义一个自然分钟内的聚合丢包告警。"""

    alerts: list[ProbeAlertRequest] = Field(min_length=1)


class ProbeAcceptedResponse(BaseModel):
    """表示中央服务已接受探测上报。"""

    accepted: bool = True


class ProbeNodeItem(BaseModel):
    """表示当前用户关联设备的一个探测源节点。"""

    id: int
    ip: str
    label: str
    online: bool


class ProbeNodesResponse(BaseModel):
    """当前用户探测源节点列表的统一响应。"""

    code: int = 200
    msg: str = "探测节点获取成功"
    data: list[ProbeNodeItem]


class ProbeTrendSeries(BaseModel):
    """保存一个目标 IP 的稠密探测趋势序列。

    lossRates 与 latenciesMs 按下标对齐查询范围内的完整时间桶轴，
    无数据的时间桶为 None。
    """

    targetIpId: int
    targetIp: str
    isp: int | None
    label: str
    lossRates: list[float | None]
    latenciesMs: list[float | None]


class ProbeProtocolSummary(BaseModel):
    """保存一个协议在报告分组中的平均探测结果。"""

    lossRate: float
    averageLatencyMs: float | None


class ProbeReportRow(BaseModel):
    """保存同省份、同运营商目标节点的三协议汇总。"""

    province: int | None
    provinceName: str
    isp: int | None
    ispName: str
    icmp: ProbeProtocolSummary | None = None
    tcp: ProbeProtocolSummary | None = None
    udp: ProbeProtocolSummary | None = None


class ProbePeriodReportRow(BaseModel):
    """保存昨日指定目标网络和时段内的三协议平均探测结果。"""

    province: int | None
    provinceName: str
    isp: int | None
    ispName: str
    period: Literal["full_day", "evening_peak"]
    icmp: ProbeProtocolSummary | None = None
    tcp: ProbeProtocolSummary | None = None
    udp: ProbeProtocolSummary | None = None


class ProbeReportData(BaseModel):
    """保存当前节点的统计时间范围及分组报告。"""

    startTime: int
    endTime: int
    rows: list[ProbeReportRow]


class ProbeReportResponse(BaseModel):
    """探测概览报告的统一响应。"""

    code: int = 200
    msg: str = "探测概览获取成功"
    data: ProbeReportData


class ProbePreviousDayReportData(BaseModel):
    """保存北京时间昨日日期及全天、晚高峰的分时报告行。"""

    date: str
    rows: list[ProbePeriodReportRow]


class ProbePreviousDayReportResponse(BaseModel):
    """昨日探测报告的统一响应。"""

    code: int = 200
    msg: str = "昨日探测报告获取成功"
    data: ProbePreviousDayReportData


class ProbeTrendData(BaseModel):
    """保存指定查询范围、聚合粒度及其中的目标 IP 趋势序列。

    完整时间桶轴从 startTime - startTime % intervalSeconds 开始，
    以 intervalSeconds 递增至不超过 endTime，序列数组下标与之一一对应。
    """

    startTime: int
    endTime: int
    intervalSeconds: int
    series: list[ProbeTrendSeries]


class ProbeTrendResponse(BaseModel):
    """探测趋势数据的统一响应。"""

    code: int = 200
    msg: str = "探测趋势获取成功"
    data: ProbeTrendData
