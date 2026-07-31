"""微信带参数二维码路由。"""

import secrets
import string
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.wechat import QRCodeResponse, QRCodeStatusResponse
from app.services.wechat import (
    QRCODE_EXPIRE_SECONDS,
    WECHAT_QRCODE_IMAGE_URL,
    create_qrcode,
)


SCENE_RANDOM_CHARACTERS = string.ascii_uppercase + string.digits

router = APIRouter(prefix="/wechat", tags=["微信"])


def generate_scene_str() -> str:
    """生成北京时间戳与随机字符组成的场景值。

    参数:
        无。
    返回:
        16 位微信二维码字符串场景值。
    """
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%y%m%d%H%M%S")
    random_suffix = "".join(
        secrets.choice(SCENE_RANDOM_CHARACTERS) for _ in range(4)
    )
    return timestamp + random_suffix


@router.post("/qrcode", response_model=QRCodeResponse)
async def create_parameterized_qrcode() -> QRCodeResponse:
    """生成有效期为 30 分钟的微信带参数二维码。

    参数:
        无。
    返回:
        二维码场景值、ticket、有效期和访问地址。
    """
    scene_str = generate_scene_str()
    response_data = await create_qrcode(scene_str)

    ticket = response_data.get("ticket")
    url = response_data.get("url")
    expire_seconds = response_data.get("expire_seconds")
    if not isinstance(ticket, str) or not ticket:
        raise HTTPException(status_code=502, detail="微信二维码响应缺少 ticket")
    if not isinstance(url, str) or not url:
        raise HTTPException(status_code=502, detail="微信二维码响应缺少 url")
    if not isinstance(expire_seconds, int) or expire_seconds <= 0:
        raise HTTPException(status_code=502, detail="微信二维码有效期无效")

    image_url = f"{WECHAT_QRCODE_IMAGE_URL}?{urlencode({'ticket': ticket})}"
    return QRCodeResponse(
        scene_str=scene_str,
        ticket=ticket,
        expire_seconds=expire_seconds,
        url=url,
        image_url=image_url,
    )


@router.get("/qrcode/status", response_model=QRCodeStatusResponse)
def get_qrcode_status(
    scene_str: str = Query(..., min_length=16, max_length=16),
) -> QRCodeStatusResponse:
    """查询二维码场景值对应的用户登录状态。

    参数:
        scene_str: Agent 创建二维码时获得的 16 位场景值。
    返回:
        是否匹配到有效关注用户，以及匹配成功时的 openid。
    """
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.scene_str == scene_str))

    if user is None or not user.openid or user.subscribe_status != 1:
        return QRCodeStatusResponse(matched=False)
    return QRCodeStatusResponse(matched=True, openid=user.openid)
