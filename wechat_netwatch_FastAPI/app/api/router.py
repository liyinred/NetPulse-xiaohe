"""应用 API 路由汇总。"""

from fastapi import APIRouter

from app.api.routes.device import router as device_router
from app.api.routes.wechat_callback import router as callback_router
from app.api.routes.wechat_qrcode import router as qrcode_router


api_router = APIRouter()
api_router.include_router(callback_router)
api_router.include_router(qrcode_router)
api_router.include_router(device_router)
