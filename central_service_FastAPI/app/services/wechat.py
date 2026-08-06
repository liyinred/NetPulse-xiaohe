"""微信服务号 API 调用服务。"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from app.core.config import WECHAT_APP_ID, WECHAT_APP_SECRET


WECHAT_ACCESS_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
WECHAT_QRCODE_URL = "https://api.weixin.qq.com/cgi-bin/qrcode/create"
WECHAT_QRCODE_IMAGE_URL = "https://mp.weixin.qq.com/cgi-bin/showqrcode"
WECHAT_TEMPLATE_MESSAGE_URL = (
    "https://api.weixin.qq.com/cgi-bin/message/template/send"
)
PROBE_ALERT_TEMPLATE_ID = "O-GGfJtwz_5biXaKHjBfADGcIaHrdI4TT3Ajg3a6tDI"
QRCODE_EXPIRE_SECONDS = 5 * 60
ACCESS_TOKEN_REFRESH_MARGIN_SECONDS = 5 * 60
WECHAT_API_TIMEOUT_SECONDS = 10.0

_access_token = ""
_access_token_expires_at = 0.0
_access_token_lock = asyncio.Lock()


@dataclass(frozen=True)
class TemplateMessage:
    """保存一条待发送的微信模板消息。

    参数:
        openid: 接收用户的微信 openid。
        data: 模板字段名称及对应文本值。
    """

    openid: str
    data: dict[str, str]


def parse_wechat_response(
    response: httpx.Response, operation: str
) -> dict[str, Any]:
    """解析微信 API 响应并转换上游错误。

    参数:
        response: 微信 API 的 HTTP 响应。
        operation: 当前操作名称，用于生成错误信息。
    返回:
        微信 API 返回的 JSON 对象。
    """
    try:
        response.raise_for_status()
        response_data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"微信{operation}响应无效") from exc

    if not isinstance(response_data, dict):
        raise HTTPException(status_code=502, detail=f"微信{operation}响应格式无效")
    error_code = response_data.get("errcode")
    if error_code not in (None, 0):
        error_message = response_data.get("errmsg", "未知错误")
        raise HTTPException(
            status_code=502,
            detail=f"微信{operation}失败: errcode={error_code}, errmsg={error_message}",
        )
    return response_data


def validate_wechat_credentials() -> None:
    """校验调用微信 API 所需的服务号凭据。

    参数:
        无。
    返回:
        凭据完整时无返回值。
    """
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        raise HTTPException(status_code=503, detail="微信 AppID 或 AppSecret 未配置")


async def get_access_token(client: httpx.AsyncClient) -> str:
    """获取并缓存微信 AccessToken。

    参数:
        client: 用于调用微信 API 的异步 HTTP 客户端。
    返回:
        当前有效的微信 AccessToken。
    """
    global _access_token, _access_token_expires_at

    current_time = time.monotonic()
    if _access_token and current_time < _access_token_expires_at:
        return _access_token

    async with _access_token_lock:
        current_time = time.monotonic()
        if _access_token and current_time < _access_token_expires_at:
            return _access_token

        validate_wechat_credentials()
        try:
            response = await client.get(
                WECHAT_ACCESS_TOKEN_URL,
                params={
                    "grant_type": "client_credential",
                    "appid": WECHAT_APP_ID,
                    "secret": WECHAT_APP_SECRET,
                },
            )
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail="微信 AccessToken 请求失败") from exc

        response_data = parse_wechat_response(response, "AccessToken")
        access_token = response_data.get("access_token")
        expires_in = response_data.get("expires_in")
        if not isinstance(access_token, str) or not access_token:
            raise HTTPException(status_code=502, detail="微信 AccessToken 响应缺少凭据")
        if not isinstance(expires_in, int) or expires_in <= 0:
            raise HTTPException(status_code=502, detail="微信 AccessToken 有效期无效")

        _access_token = access_token
        _access_token_expires_at = current_time + max(
            expires_in - ACCESS_TOKEN_REFRESH_MARGIN_SECONDS, 0
        )
        return _access_token


async def create_qrcode_ticket(
    client: httpx.AsyncClient, access_token: str, scene_str: str
) -> dict[str, Any]:
    """调用微信 API 创建临时字符串二维码 ticket。

    参数:
        client: 用于调用微信 API 的异步 HTTP 客户端。
        access_token: 微信接口调用凭据。
        scene_str: 二维码携带的字符串场景值。
    返回:
        微信 API 返回的二维码信息。
    """
    try:
        response = await client.post(
            WECHAT_QRCODE_URL,
            params={"access_token": access_token},
            json={
                "expire_seconds": QRCODE_EXPIRE_SECONDS,
                "action_name": "QR_STR_SCENE",
                "action_info": {"scene": {"scene_str": scene_str}},
            },
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="微信二维码请求失败") from exc
    return parse_wechat_response(response, "二维码创建")


async def create_qrcode(scene_str: str) -> dict[str, Any]:
    """获取 AccessToken 并创建微信二维码。

    参数:
        scene_str: 二维码携带的字符串场景值。
    返回:
        微信 API 返回的二维码信息。
    """
    validate_wechat_credentials()
    async with httpx.AsyncClient(timeout=WECHAT_API_TIMEOUT_SECONDS) as client:
        access_token = await get_access_token(client)
        return await create_qrcode_ticket(client, access_token, scene_str)


async def send_template_message(
    client: httpx.AsyncClient,
    access_token: str,
    message: TemplateMessage,
) -> dict[str, Any]:
    """调用微信 API 发送一条丢包告警模板消息。

    参数:
        client: 用于调用微信 API 的异步 HTTP 客户端。
        access_token: 微信接口调用凭据。
        message: 接收用户及模板字段数据。
    返回:
        微信 API 返回的模板消息发送结果。
    """
    try:
        response = await client.post(
            WECHAT_TEMPLATE_MESSAGE_URL,
            params={"access_token": access_token},
            json={
                "touser": message.openid,
                "template_id": PROBE_ALERT_TEMPLATE_ID,
                "data": {
                    key: {"value": value}
                    for key, value in message.data.items()
                },
            },
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="微信模板消息请求失败") from exc
    return parse_wechat_response(response, "模板消息发送")


async def send_template_messages(
    messages: list[TemplateMessage],
) -> None:
    """复用同一 AccessToken 依次发送多条模板消息。

    参数:
        messages: 待发送的微信模板消息列表。
    返回:
        无返回值；任一微信请求失败时抛出 HTTPException。
    """
    if not messages:
        return
    validate_wechat_credentials()
    async with httpx.AsyncClient(timeout=WECHAT_API_TIMEOUT_SECONDS) as client:
        access_token = await get_access_token(client)
        for message in messages:
            await send_template_message(client, access_token, message)
