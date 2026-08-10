"""FastAPI 应用创建与启动入口。"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.models  # noqa: F401
from app.api.router import api_router
from app.db.base import Base
from app.db.session import engine


logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """在应用启动时创建缺失的数据库表。

    参数:
        application: 当前 FastAPI 应用实例。
    返回:
        控制应用生命周期的异步迭代器。
    """
    Base.metadata.create_all(bind=engine)
    yield


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。

    参数:
        无。
    返回:
        已注册业务路由的 FastAPI 应用。
    """
    application = FastAPI(title="central_service_FastAPI", lifespan=lifespan)
    application.include_router(api_router)
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
