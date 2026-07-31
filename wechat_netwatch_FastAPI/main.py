"""FastAPI 应用创建与启动入口。"""

import logging

from fastapi import FastAPI

from app.api.router import api_router


logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用。

    参数:
        无。
    返回:
        已注册业务路由的 FastAPI 应用。
    """
    application = FastAPI(title="wechat_netwatch_FastAPI")
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
