"""微信带参数二维码路由。"""

from ipaddress import IPv4Address, IPv6Address
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query

from app.schemas.device import build_device_network_info
from app.schemas.wechat import QRCodeResponse, QRCodeStatusResponse
from app.services.device import bind_device_by_scene
from app.services.network import IPLookupError
from app.services.wechat import (
    WECHAT_QRCODE_IMAGE_URL,
    create_qrcode,
    generate_scene_str,
)

router = APIRouter(prefix="/wechat", tags=["微信"])

@router.post("/qrcode", response_model=QRCodeResponse)
async def create_parameterized_qrcode() -> QRCodeResponse:
    """生成有效期为 5 分钟的微信带参数二维码。

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
async def get_qrcode_status(
    scene_str: str = Query(..., min_length=16, max_length=16),
    device_id: str = Query(..., min_length=1, max_length=64),
    source_ipv4: IPv4Address = Query(...),
    source_ipv6: IPv6Address | None = Query(None),
) -> QRCodeStatusResponse:
    """查询二维码状态，并在匹配成功时直接绑定设备。

    参数:
        scene_str: Agent 创建二维码时获得的 16 位场景值。
        device_id: Agent 本地持久化的设备标识。
        source_ipv4: 本次启动获取到的公网 IPv4。
        source_ipv6: 本次启动获取到的公网 IPv6，未获取到时为空。
    返回:
        是否已匹配有效关注用户并完成设备绑定。
    """
    try:
        binding_result = await bind_device_by_scene(
            device_id,
            scene_str,
            source_ipv4,
            source_ipv6,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IPLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if binding_result is None:
        return QRCodeStatusResponse(matched=False)
    return QRCodeStatusResponse(
        matched=True,
        device=build_device_network_info(binding_result),
    )
