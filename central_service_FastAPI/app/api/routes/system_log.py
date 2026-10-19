"""管理员系统日志与 Prometheus 指标路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.responses import Response

from app.models.user import User
from app.schemas.pagination import PaginationParams
from app.schemas.system_log import HttpErrorLogListResponse, HttpMetricsResponse
from app.services.auth import get_current_admin
from app.services.http_observability import (
    get_http_metrics,
    list_http_error_logs,
    render_prometheus_metrics,
)


router = APIRouter(prefix="/api/system-logs", tags=["系统日志"])
prometheus_router = APIRouter(tags=["Prometheus"])
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get("/list", response_model=HttpErrorLogListResponse)
def get_http_error_log_list(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(get_current_admin)],
) -> HttpErrorLogListResponse:
    """查询 HTTP 5xx 错误日志分页列表。

    参数:
        pagination: current、size、sortField、sortOrder 分页协议。
        _: 管理员认证依赖解析出的当前用户。
    返回:
        默认按发生时间降序排列的 HTTP 错误日志。
    """
    return HttpErrorLogListResponse(data=list_http_error_logs(pagination))


@router.get("/metrics", response_model=HttpMetricsResponse)
def get_system_http_metrics(
    _: Annotated[User, Depends(get_current_admin)],
) -> HttpMetricsResponse:
    """获取当前 FastAPI 进程的 HTTP 指标快照。

    参数:
        _: 管理员认证依赖解析出的当前用户。
    返回:
        运行时长、请求数、5xx 数及请求耗时统计。
    """
    return HttpMetricsResponse(data=get_http_metrics())


@prometheus_router.get("/metrics", include_in_schema=False)
def get_prometheus_metrics() -> Response:
    """输出 Prometheus text exposition 格式指标。

    参数:
        无。
    返回:
        Prometheus 可抓取的指标文本响应。
    """
    return Response(
        render_prometheus_metrics(),
        headers={"Content-Type": PROMETHEUS_CONTENT_TYPE},
    )
