"""HTTP 指标统计与 5xx 错误日志持久化服务。"""

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from math import ceil
from threading import Lock
from time import monotonic, time
from typing import Literal

from sqlalchemy import create_engine, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.config import HTTP_ERROR_LOG_DATABASE_PATH
from app.models.http_error_log import HttpErrorLog, HttpErrorLogBase
from app.schemas.pagination import PaginatedData, PaginationParams
from app.schemas.system_log import HttpErrorLogItem, HttpMetrics
from app.services.pagination import paginate_query


logger = logging.getLogger(__name__)
BEIJING_TIMEZONE = timezone(timedelta(hours=8))
MAX_ERROR_MESSAGE_LENGTH = 2000
MAX_DURATION_SAMPLES = 10_000
HTTP_ERROR_RETENTION_DAYS = 7
PROCESS_STARTED_AT = monotonic()

http_error_engine = create_engine(
    f"sqlite:///{HTTP_ERROR_LOG_DATABASE_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)
HttpErrorSessionLocal = sessionmaker(
    bind=http_error_engine,
    autoflush=False,
    expire_on_commit=False,
)

_metrics_lock = Lock()
_request_total = 0
_http_5xx_total = 0
_duration_request_total = 0
_duration_total_seconds = 0.0
_duration_samples: deque[float] = deque(maxlen=MAX_DURATION_SAMPLES)

HTTP_ERROR_SORT_COLUMNS = {
    "id": HttpErrorLog.id,
    "direction": HttpErrorLog.direction,
    "method": HttpErrorLog.method,
    "path": HttpErrorLog.path,
    "statusCode": HttpErrorLog.status_code,
    "errorType": HttpErrorLog.error_type,
    "occurredTime": HttpErrorLog.occurred_time,
}


def initialize_http_error_database() -> None:
    """创建 HTTP 错误日志 SQLite 目录和缺失表。

    参数:
        无。
    返回:
        无返回值。
    """
    HTTP_ERROR_LOG_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    HttpErrorLogBase.metadata.create_all(bind=http_error_engine)


def record_inbound_metrics(
    method: str,
    status_code: int,
    duration_seconds: float,
    include_duration: bool = True,
) -> None:
    """记录一次 inbound HTTP 请求的 Prometheus 指标。

    参数:
        method: HTTP method。
        status_code: HTTP 响应状态码。
        duration_seconds: 请求处理耗时，单位为秒。
        include_duration: 是否将本次请求纳入普通业务 API 耗时统计。
    返回:
        无返回值。
    """
    global _request_total, _http_5xx_total
    global _duration_request_total, _duration_total_seconds

    with _metrics_lock:
        _request_total += 1
        if status_code >= 500:
            _http_5xx_total += 1
        if include_duration:
            _duration_request_total += 1
            _duration_total_seconds += duration_seconds
            _duration_samples.append(duration_seconds)


def record_http_error(
    direction: Literal["inbound", "outbound"],
    method: str,
    path: str,
    status_code: int,
    error_type: str,
    error_message: str,
) -> None:
    """写入一条 HTTP 5xx 错误并清理七个完整自然日前的记录。

    参数:
        direction: 请求方向，支持 inbound 或 outbound。
        method: HTTP method。
        path: route path 或原始请求路径。
        status_code: HTTP 5xx 响应状态码。
        error_type: 错误类型名称。
        error_message: 错误消息，最多保存 2000 字符。
    返回:
        无返回值；写库失败时仅记录应用日志，避免影响原请求。
    """
    if status_code < 500 or status_code > 599:
        return
    occurred_time = int(time())
    record = HttpErrorLog(
        direction=direction,
        method=method.upper(),
        path=path,
        status_code=status_code,
        error_type=error_type,
        error_message=error_message[:MAX_ERROR_MESSAGE_LENGTH],
        occurred_time=occurred_time,
    )
    try:
        with HttpErrorSessionLocal.begin() as session:
            retention_cutoff = _get_http_error_retention_cutoff(occurred_time)
            session.execute(
                delete(HttpErrorLog).where(
                    HttpErrorLog.occurred_time < retention_cutoff
                )
            )
            session.add(record)
    except SQLAlchemyError:
        logger.exception("HTTP 5xx 错误日志写入 SQLite 失败")


def _get_http_error_retention_cutoff(occurred_time: int) -> int:
    """计算 HTTP 错误日志最近七个完整自然日的保留边界。

    参数:
        occurred_time: 当前新增记录的 Unix 时间戳，单位为秒。
    返回:
        北京时间当天零点向前七日对应的 Unix 时间戳。
    """
    current_day_start = datetime.fromtimestamp(
        occurred_time,
        tz=BEIJING_TIMEZONE,
    ).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        (current_day_start - timedelta(days=HTTP_ERROR_RETENTION_DAYS)).timestamp()
    )


def record_outbound_response_error(status_code: int, method: str, path: str) -> None:
    """记录外部服务返回的 HTTP 5xx 响应。

    参数:
        status_code: 外部服务 HTTP 响应状态码。
        method: outbound HTTP method。
        path: 不含敏感 query 的外部请求路径。
    返回:
        无返回值。
    """
    record_http_error(
        direction="outbound",
        method=method,
        path=path,
        status_code=status_code,
        error_type="HTTPStatusError",
        error_message=f"外部服务返回 HTTP {status_code}",
    )


def _percentile(sorted_samples: list[float], percentile: float) -> float:
    """计算有序耗时样本的 nearest-rank 百分位值。

    参数:
        sorted_samples: 已按升序排列的秒级耗时样本。
        percentile: 0 至 1 之间的百分位比例。
    返回:
        对应百分位耗时；没有样本时返回 0。
    """
    if not sorted_samples:
        return 0.0
    index = max(ceil(len(sorted_samples) * percentile) - 1, 0)
    return sorted_samples[index]


def get_http_metrics() -> HttpMetrics:
    """读取当前 FastAPI 进程的 HTTP 指标快照。

    参数:
        无。
    返回:
        运行时长、请求数、5xx 数及毫秒级耗时指标。
    """
    with _metrics_lock:
        request_total = _request_total
        http_5xx_total = _http_5xx_total
        duration_request_total = _duration_request_total
        duration_total_seconds = _duration_total_seconds
        duration_samples = sorted(_duration_samples)
    average_seconds = (
        duration_total_seconds / duration_request_total
        if duration_request_total
        else 0.0
    )
    return HttpMetrics(
        processUptimeSeconds=int(monotonic() - PROCESS_STARTED_AT),
        httpRequestTotal=request_total,
        http5xxTotal=http_5xx_total,
        averageRequestDurationMs=round(average_seconds * 1000, 2),
        p95RequestDurationMs=round(_percentile(duration_samples, 0.95) * 1000, 2),
        p99RequestDurationMs=round(_percentile(duration_samples, 0.99) * 1000, 2),
    )


def render_prometheus_metrics() -> bytes:
    """生成 Prometheus text exposition 格式的指标内容。

    参数:
        无。
    返回:
        Prometheus client registry 的 UTF-8 字节内容。
    """
    metrics = get_http_metrics()
    with _metrics_lock:
        request_total = _request_total
        http_5xx_total = _http_5xx_total
        duration_request_total = _duration_request_total
        duration_total_seconds = _duration_total_seconds
    lines = [
        "# HELP netpulse_process_uptime_seconds FastAPI process uptime in seconds.",
        "# TYPE netpulse_process_uptime_seconds gauge",
        f"netpulse_process_uptime_seconds {metrics.processUptimeSeconds}",
        "# HELP netpulse_http_requests_total FastAPI inbound HTTP requests.",
        "# TYPE netpulse_http_requests_total counter",
        f"netpulse_http_requests_total {request_total}",
        "# HELP netpulse_http_5xx_total FastAPI inbound HTTP 5xx responses.",
        "# TYPE netpulse_http_5xx_total counter",
        f"netpulse_http_5xx_total {http_5xx_total}",
        "# HELP netpulse_http_request_duration_seconds FastAPI business API request duration.",
        "# TYPE netpulse_http_request_duration_seconds summary",
        (
            'netpulse_http_request_duration_seconds{quantile="0.95"} '
            f"{metrics.p95RequestDurationMs / 1000}"
        ),
        (
            'netpulse_http_request_duration_seconds{quantile="0.99"} '
            f"{metrics.p99RequestDurationMs / 1000}"
        ),
        (
            "netpulse_http_request_duration_seconds_sum "
            f"{duration_total_seconds}"
        ),
        f"netpulse_http_request_duration_seconds_count {duration_request_total}",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _build_http_error_log_item(record: HttpErrorLog) -> HttpErrorLogItem:
    """将 SQLite ORM 记录转换为系统日志列表项。

    参数:
        record: HTTP 错误日志 ORM 记录。
    返回:
        发生时间已转换为北京时间的日志列表项。
    """
    occurred_time = datetime.fromtimestamp(
        record.occurred_time,
        tz=BEIJING_TIMEZONE,
    ).strftime("%Y-%m-%d %H:%M:%S")
    return HttpErrorLogItem(
        id=record.id,
        direction=record.direction,
        method=record.method,
        path=record.path,
        statusCode=record.status_code,
        errorType=record.error_type,
        errorMessage=record.error_message,
        occurredTime=occurred_time,
    )


def list_http_error_logs(pagination: PaginationParams) -> PaginatedData[HttpErrorLogItem]:
    """按发生时间降序查询 HTTP 5xx 错误日志。

    参数:
        pagination: 统一分页和排序参数。
    返回:
        HTTP 错误日志记录及分页信息。
    """
    with HttpErrorSessionLocal() as session:
        records, total = paginate_query(
            session,
            select(HttpErrorLog),
            pagination,
            HTTP_ERROR_SORT_COLUMNS,
            "occurredTime",
            HttpErrorLog.id,
        )
        items = [_build_http_error_log_item(record) for record in records]
    return PaginatedData(
        records=items,
        current=pagination.current,
        size=pagination.size,
        total=total,
    )
