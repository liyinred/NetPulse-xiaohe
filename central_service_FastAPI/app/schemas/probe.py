"""持续探测 API 数据模型。"""

from ipaddress import IPv4Address, IPv6Address
from typing import Literal

from pydantic import BaseModel, Field


ProbeMode = Literal["cross_isp", "cross_province"]
ProtocolType = Literal["icmp", "tcp", "udp"]


class ProbeTarget(BaseModel):
    """保存中央服务下发的单个公开探测目标。"""

    public_ip: IPv4Address | IPv6Address
    isp: int
    province: int


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
    average_latency_ms: int = Field(ge=0)


class TargetProbeResult(BaseModel):
    """保存一个目标的 ICMP、TCP 和 UDP 汇总结果。"""

    target_ip: IPv4Address | IPv6Address
    icmp: ProtocolProbeResult
    tcp: ProtocolProbeResult
    udp: ProtocolProbeResult


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
