"""网页登录认证数据模型。"""

from typing import Literal

from pydantic import BaseModel


class WechatQRCodeData(BaseModel):
    """网页登录微信二维码数据。"""

    sceneStr: str
    expireSeconds: int
    url: str
    imageUrl: str


class WechatQRCodeResponse(BaseModel):
    """网页登录微信二维码响应。"""

    code: int = 200
    msg: str = "二维码创建成功"
    data: WechatQRCodeData


class WechatLoginStatusData(BaseModel):
    """微信扫码登录轮询数据。"""

    status: Literal["pending", "authenticated", "expired"]
    token: str | None = None


class WechatLoginStatusResponse(BaseModel):
    """微信扫码登录轮询响应。"""

    code: int = 200
    msg: str = "登录状态查询成功"
    data: WechatLoginStatusData


class UserInfoData(BaseModel):
    """当前网页登录用户信息。"""

    buttons: list[str]
    roles: list[str]
    userId: int
    userName: str
    email: str
    userLevel: int
    avatar: str | None = None


class UserInfoResponse(BaseModel):
    """当前网页登录用户信息响应。"""

    code: int = 200
    msg: str = "用户信息获取成功"
    data: UserInfoData
