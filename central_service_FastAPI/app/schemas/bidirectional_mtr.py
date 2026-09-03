"""双向 MTR API 数据模型。"""

from ipaddress import IPv4Address, IPv6Address
from typing import Literal

from pydantic import BaseModel, Field


MTRStatus = Literal["queued", "running", "completed", "partial_completed", "failed"]


class MTRDeviceIP(BaseModel):
    """保存用户可选择的在线设备公网 IP。"""

    id: int
    ip: str
    ipVersion: Literal[4, 6]


class MTRDevice(BaseModel):
    """保存双向 MTR 的一个在线节点及其可选地址。"""

    id: int
    nodeName: str
    ips: list[MTRDeviceIP]


class MTRDeviceListResponse(BaseModel):
    """包装当前用户可用于双向 MTR 的设备列表。"""

    code: int = 200
    msg: str = "双向 MTR 在线设备获取成功"
    data: list[MTRDevice]


class CreateMTRRequest(BaseModel):
    """定义用户创建双向 MTR 主任务的请求。"""

    sourceDeviceId: int = Field(gt=0)
    sourceIpId: int = Field(gt=0)
    targetDeviceId: int = Field(gt=0)
    targetIpId: int = Field(gt=0)


class CreateMTRData(BaseModel):
    """保存新建双向 MTR 主任务的标识和状态。"""

    mtrTaskId: int
    status: MTRStatus


class CreateMTRResponse(BaseModel):
    """包装双向 MTR 创建结果。"""

    code: int = 200
    msg: str = "双向 MTR 已创建"
    data: CreateMTRData


class MTRHop(BaseModel):
    """保存单个 TTL 的 MTR 统计结果。"""

    ttl: int = Field(ge=1, le=32)
    address: str | None = None
    sent: int = Field(ge=0, le=10)
    received: int = Field(ge=0, le=10)
    lossRate: int = Field(ge=0, le=1000)
    averageLatencyMs: int | None = Field(default=None, ge=0, le=3000)


class MTRDirectionResult(BaseModel):
    """保存一个方向的展示状态、地址快照和逐跳结果。"""

    direction: Literal["A_TO_B", "B_TO_A"]
    sourceIp: str
    targetIp: str
    status: MTRStatus
    errorCode: str | None = None
    hops: list[MTRHop]


class MTRTaskResult(BaseModel):
    """保存双向 MTR 主任务的聚合结果。"""

    mtrTaskId: int
    status: MTRStatus
    directions: list[MTRDirectionResult]


class MTRTaskResultResponse(BaseModel):
    """包装双向 MTR 查询结果。"""

    code: int = 200
    msg: str = "双向 MTR 结果获取成功"
    data: MTRTaskResult


class MTRAgentTask(BaseModel):
    """保存 Agent 领取的单方向 MTR 任务及地址快照。"""

    mtr_task_id: int
    direction: Literal["A_TO_B", "B_TO_A"]
    lease_token: str
    source_ip: IPv4Address | IPv6Address
    target_ip: IPv4Address | IPv6Address
    ip_version: Literal[4, 6]


class MTRAgentTaskResponse(BaseModel):
    """包装 Agent 长轮询的单方向 MTR 任务。"""

    data: MTRAgentTask | None = None


class MTRResultRequest(BaseModel):
    """定义 Agent 对单方向 MTR 的幂等结果上报。"""

    mtr_task_id: int = Field(gt=0)
    direction: Literal["A_TO_B", "B_TO_A"]
    lease_token: str = Field(min_length=32, max_length=64)
    device_id: str = Field(min_length=1, max_length=64)
    source_ip: IPv4Address | IPv6Address
    target_ip: IPv4Address | IPv6Address
    started_at: int = Field(gt=0)
    finished_at: int = Field(gt=0)
    hops: list[MTRHop] = Field(max_length=32)
    error_code: str | None = Field(default=None, max_length=64)


class MTRAcceptedResponse(BaseModel):
    """表示中央服务已接受 MTR 结果。"""

    accepted: bool = True
