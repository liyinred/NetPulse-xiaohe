"""FastAPI 应用创建与启动入口。"""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse, Response
from starlette.types import Scope

import app.models  # noqa: F401
from app.api.router import api_router
from app.db.base import Base
from app.db.session import engine
from app.middleware.http_observability import HttpObservabilityMiddleware
from app.services.data_retention import run_probe_retention_scheduler
from app.services.http_observability import initialize_http_error_database


logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

FRONTEND_DIST_DIR = Path(__file__).resolve().parents[2] / "frontend_Vue3" / "dist"


class FrontendStaticFiles(StaticFiles):
    """提供禁用 HTML 缓存的前端静态文件服务。"""

    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        """创建静态文件响应，并禁止浏览器缓存 HTML 文件。

        参数:
            full_path: 静态文件的完整路径。
            stat_result: 静态文件的状态信息。
            scope: 当前 ASGI 请求上下文。
            status_code: HTTP 响应状态码。
        返回:
            已配置缓存策略的静态文件响应。
        """
        if Path(full_path).suffix.lower() != ".html":
            return super().file_response(full_path, stat_result, scope, status_code)

        response = FileResponse(
            full_path,
            status_code=status_code,
            stat_result=stat_result,
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """在应用启动时创建缺失的数据库表并启动探测数据保留清理任务。

    参数:
        application: 当前 FastAPI 应用实例。
    返回:
        控制应用生命周期的异步迭代器；应用关闭时取消清理任务。
    """
    Base.metadata.create_all(bind=engine)
    initialize_http_error_database()
    retention_task = asyncio.create_task(run_probe_retention_scheduler())
    yield
    retention_task.cancel()
    with suppress(asyncio.CancelledError):
        await retention_task


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。

    参数:
        无。
    返回:
        已注册业务路由并挂载前端构建产物的 FastAPI 应用。
    """
    application = FastAPI(title="central_service_FastAPI", lifespan=lifespan)
    application.add_middleware(HttpObservabilityMiddleware)
    application.include_router(api_router)
    application.mount(
        "/",
        FrontendStaticFiles(directory=FRONTEND_DIST_DIR, html=True),
        name="frontend",
    )
    return application


app = create_app()


def main() -> None:
    """启动 Uvicorn HTTP 服务。

    参数:
        无。
    返回:
        无返回值；函数会阻塞运行 HTTP 服务。
    """
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8086)


if __name__ == "__main__":
    main()
