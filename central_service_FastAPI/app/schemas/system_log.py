"""系统日志与 HTTP 指标 API 数据模型。"""

from typing import Literal

from pydantic import BaseModel

from app.schemas.pagination import PaginatedData


class HttpErrorLogItem(BaseModel):
    """HTTP 5xx 错误日志列表项。"""

    id: int
    direction: Literal["inbound", "outbound"]
    method: str
    path: str
    statusCode: int
    errorType: str
    errorMessage: str
    occurredTime: str


class HttpErrorLogListResponse(BaseModel):
    """HTTP 5xx 错误日志分页响应。"""

    code: int = 200
    msg: str = "系统日志获取成功"
    data: PaginatedData[HttpErrorLogItem]


class HttpMetrics(BaseModel):
    """当前 FastAPI 进程的 HTTP Prometheus 指标快照。"""

    processUptimeSeconds: int
    httpRequestTotal: int
    http5xxTotal: int
    averageRequestDurationMs: float
    p95RequestDurationMs: float
    p99RequestDurationMs: float


class HttpMetricsResponse(BaseModel):
    """HTTP Prometheus 指标统一响应。"""

    code: int = 200
    msg: str = "Prometheus 指标获取成功"
    data: HttpMetrics
