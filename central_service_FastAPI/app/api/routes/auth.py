"""微信扫码 JWT 登录路由。"""

from time import time
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.routes.wechat_qrcode import create_parameterized_qrcode
from app.models.user import User
from app.schemas.auth import (
    UserInfoData,
    UserInfoResponse,
    WechatLoginStatusData,
    WechatLoginStatusResponse,
    WechatQRCodeData,
    WechatQRCodeResponse,
)
from app.services.auth import (
    create_access_token,
    find_login_user,
    get_current_user,
    get_user_roles,
)
from app.services.wechat import QRCODE_EXPIRE_SECONDS, get_scene_created_at


router = APIRouter(prefix="/api", tags=["网页认证"])


@router.post("/auth/wechat/qrcode", response_model=WechatQRCodeResponse)
async def create_login_qrcode() -> WechatQRCodeResponse:
    """创建用于网页登录的临时微信服务号二维码。

    参数:
        无。
    返回:
        统一响应格式的二维码参数和有效期。
    """
    qrcode = await create_parameterized_qrcode()
    return WechatQRCodeResponse(
        data=WechatQRCodeData(
            sceneStr=qrcode.scene_str,
            expireSeconds=qrcode.expire_seconds,
            url=qrcode.url,
            imageUrl=qrcode.image_url,
        )
    )


@router.get("/auth/wechat/status", response_model=WechatLoginStatusResponse)
async def get_login_status(
    scene_str: str = Query(..., min_length=16, max_length=16),
) -> WechatLoginStatusResponse:
    """轮询微信二维码状态并在扫码成功后签发 JWT。

    参数:
        scene_str: 创建二维码时返回的 16 字符场景值。
    返回:
        pending、expired 或携带 JWT 的 authenticated 状态。
    """
    created_at = get_scene_created_at(scene_str)
    if created_at is None or int(time()) - created_at > QRCODE_EXPIRE_SECONDS:
        return WechatLoginStatusResponse(
            data=WechatLoginStatusData(status="expired")
        )
    user = find_login_user(scene_str)
    if user is None:
        return WechatLoginStatusResponse(
            data=WechatLoginStatusData(status="pending")
        )
    return WechatLoginStatusResponse(
        data=WechatLoginStatusData(
            status="authenticated",
            token=create_access_token(user.id),
        )
    )


@router.get("/user/info", response_model=UserInfoResponse)
async def get_user_info(
    user: Annotated[User, Depends(get_current_user)],
) -> UserInfoResponse:
    """返回当前 JWT 用户的前端基础资料。

    参数:
        user: JWT 认证依赖解析出的微信用户。
    返回:
        前端路由守卫所需的用户、角色和权限信息。
    """
    return UserInfoResponse(
        data=UserInfoData(
            buttons=[],
            roles=get_user_roles(user.user_level),
            userId=user.id,
            userName=f"微信用户 {user.id}",
            email="",
            userLevel=user.user_level,
        )
    )
