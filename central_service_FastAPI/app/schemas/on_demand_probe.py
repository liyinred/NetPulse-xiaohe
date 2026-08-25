"""临时 IP 按需探测 API 数据模型。"""

from ipaddress import IPv4Address, IPv6Address
from typing import Literal

from pydantic import BaseModel, Field


OnDemandStatus = Literal["queued", "running", "completed", "partial_completed", "failed"]


class CreateProbeQueryRequest(BaseModel):
    """定义网页登录用户创建临时 IP 查询的请求。"""

    target_ip: IPv4Address | IPv6Address = Field(alias="targetIp")


class CreateProbeQueryData(BaseModel):
    """保存新建临时 IP 查询的标识和初始状态。"""

    queryId: int
    executionId: int
    status: OnDemandStatus
    targetIp: str


class CreateProbeQueryResponse(BaseModel):
    """包装临时 IP 查询创建结果。"""

    code: int = 200
    msg: str = "临时 IP 探测已创建"
    data: CreateProbeQueryData


class ProtocolOnDemandResult(BaseModel):
    """保存按需探测中一种协议的汇总结果。"""

    loss_rate: int = Field(ge=0, le=1000)
    average_latency_ms: int = Field(ge=0, le=300)


class OnDemandNodeResult(BaseModel):
    """保存一个已完成探测节点的展示结果。"""

    sourceIpId: int
    isp: int | None
    province: int | None
    icmp: ProtocolOnDemandResult
    tcp: ProtocolOnDemandResult
    udp: ProtocolOnDemandResult


class OnDemandResultGroups(BaseModel):
    """按异网和跨省分类保存已完成的节点结果。"""

    crossIspResults: list[OnDemandNodeResult]
    crossProvinceResults: list[OnDemandNodeResult]


class ProbeQueryResultData(BaseModel):
    """保存用户可见的临时 IP 查询进度和聚合结果。"""

    executionId: int
    status: OnDemandStatus
    targetIp: str
    ipVersion: Literal[4, 6]
    targetIsp: int | None
    targetProvince: int | None
    totalNodeCount: int
    pendingNodeCount: int
    runningNodeCount: int
    completedNodeCount: int
    timeoutNodeCount: int
    failedNodeCount: int
    results: OnDemandResultGroups


class ProbeQueryResultResponse(BaseModel):
    """包装当前用户的临时 IP 查询结果。"""

    code: int = 200
    msg: str = "临时 IP 探测结果获取成功"
    data: ProbeQueryResultData


class OnDemandTaskData(BaseModel):
    """保存 Agent 领取的单个按需探测任务。"""

    id: int
    source_ip: IPv4Address | IPv6Address
    target_ip: IPv4Address | IPv6Address
    ip_version: Literal[4, 6]
    probe_count: Literal[10] = 10
    interval_ms: Literal[100] = 100
    timeout_ms: Literal[300] = 300


class OnDemandTaskResponse(BaseModel):
    """返回 Agent 当前领取的任务，无任务时 data 为空。"""

    data: OnDemandTaskData | None = None


class OnDemandProtocolResults(BaseModel):
    """保存节点按需探测的三协议完整结果。"""

    icmp: ProtocolOnDemandResult
    tcp: ProtocolOnDemandResult
    udp: ProtocolOnDemandResult


class OnDemandResultRequest(BaseModel):
    """定义 Agent 幂等上报节点按需探测结果的请求。"""

    task_id: int = Field(gt=0)
    device_id: str = Field(min_length=1, max_length=64)
    source_ip: IPv4Address | IPv6Address
    target_ip: IPv4Address | IPv6Address
    started_at: int = Field(gt=0)
    finished_at: int = Field(gt=0)
    results: OnDemandProtocolResults


class OnDemandAcceptedResponse(BaseModel):
    """表示中央服务已接受节点按需探测结果。"""

    accepted: bool = True
