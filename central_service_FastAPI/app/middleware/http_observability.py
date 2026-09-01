"""HTTP 指标与 inbound 5xx 错误捕获 middleware。"""

import json
from http import HTTPStatus
from time import perf_counter
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.http_observability import record_http_error, record_inbound_metrics


EXCLUDED_DURATION_PATHS = {
    "/api/system-logs/list",
    "/api/system-logs/metrics",
    "/docs",
    "/metrics",
    "/openapi.json",
    "/probes/on-demand/tasks",
    "/redoc",
}


class HttpObservabilityMiddleware:
    """统计 HTTP 请求指标并持久化 inbound 5xx 错误。"""

    def __init__(self, app: ASGIApp) -> None:
        """保存下游 ASGI 应用。

        参数:
            app: 要包装的 ASGI 应用。
        返回:
            无返回值。
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """处理一次 ASGI 调用并记录 HTTP 可观测性数据。

        参数:
            scope: ASGI 请求上下文。
            receive: ASGI 消息接收函数。
            send: ASGI 消息发送函数。
        返回:
            无返回值。
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        status_code = 500
        response_body = bytearray()

        async def send_wrapper(message: Message) -> None:
            """截获响应状态后继续发送 ASGI 消息。

            参数:
                message: 下游应用产生的 ASGI 消息。
            返回:
                无返回值。
            """
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body" and status_code >= 500:
                remaining_length = 2000 - len(response_body)
                if remaining_length > 0:
                    response_body.extend(message.get("body", b"")[:remaining_length])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            duration_seconds = perf_counter() - started_at
            record_inbound_metrics(
                scope["method"],
                500,
                duration_seconds,
                include_duration=self._should_record_duration(scope),
            )
            record_http_error(
                direction="inbound",
                method=scope["method"],
                path=self._resolve_request_path(scope),
                status_code=500,
                error_type=type(exc).__name__,
                error_message=str(exc) or repr(exc),
            )
            raise

        duration_seconds = perf_counter() - started_at
        record_inbound_metrics(
            scope["method"],
            status_code,
            duration_seconds,
            include_duration=self._should_record_duration(scope),
        )
        if status_code >= 500:
            error_type, error_message = self._resolve_response_error(
                status_code,
                bytes(response_body),
            )
            record_http_error(
                direction="inbound",
                method=scope["method"],
                path=self._resolve_request_path(scope),
                status_code=status_code,
                error_type=error_type,
                error_message=error_message,
            )

    @staticmethod
    def _resolve_request_path(scope: Scope) -> str:
        """优先读取 FastAPI route path，无法识别时使用原始请求路径。

        参数:
            scope: ASGI 请求上下文。
        返回:
            route path 或原始 URL path。
        """
        route: Any = scope.get("route")
        route_path = getattr(route, "path", None)
        return route_path if isinstance(route_path, str) else scope.get("path", "")

    @staticmethod
    def _should_record_duration(scope: Scope) -> bool:
        """判断当前请求是否应纳入普通业务 API 耗时统计。

        参数:
            scope: ASGI 请求上下文。
        返回:
            普通业务 API 返回 true；长轮询、指标、文档和前端静态请求返回 false。
        """
        if scope.get("path", "") in EXCLUDED_DURATION_PATHS:
            return False
        route: Any = scope.get("route")
        return getattr(route, "name", None) != "frontend"

    @staticmethod
    def _resolve_response_error(status_code: int, response_body: bytes) -> tuple[str, str]:
        """从 HTTP 5xx 响应体提取错误类型和消息。

        参数:
            status_code: HTTP 5xx 响应状态码。
            response_body: 最多 2000 字节的响应体片段。
        返回:
            错误类型和可展示的错误消息。
        """
        try:
            status_message = HTTPStatus(status_code).phrase
        except ValueError:
            status_message = "Server Error"
        fallback_message = f"HTTP {status_code} {status_message}"
        if not response_body:
            return "HTTPResponseError", fallback_message
        decoded_body = response_body.decode("utf-8", errors="replace")
        try:
            payload = json.loads(decoded_body)
        except json.JSONDecodeError:
            return "HTTPResponseError", decoded_body or fallback_message
        if isinstance(payload, dict) and payload.get("detail") is not None:
            return "HTTPException", str(payload["detail"])
        return "HTTPResponseError", decoded_body or fallback_message
