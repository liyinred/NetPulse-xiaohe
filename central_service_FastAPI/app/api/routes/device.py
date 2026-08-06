"""设备绑定路由。"""

from fastapi import APIRouter, HTTPException

from app.schemas.device import (
    DeviceBindRequest,
    DeviceBindResponse,
    build_device_network_info,
)
from app.services.device import bind_device_by_scene
from app.services.network import IPLookupError


router = APIRouter(prefix="/devices", tags=["设备"])


@router.post("/bind", response_model=DeviceBindResponse)
async def bind_device(binding: DeviceBindRequest) -> DeviceBindResponse:
    """使用二维码场景值和当前公网地址绑定设备。

    参数:
        binding: 包含设备标识和二维码场景值的绑定信息。
    返回:
        新建或更新后的设备标识、公网 IPv4 及归一化网络属性。
    """
    try:
        binding_result = await bind_device_by_scene(
            binding.device_id,
            binding.scene_str,
            binding.source_ipv4,
            binding.source_ipv6,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IPLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if binding_result is None:
        raise HTTPException(status_code=404, detail="二维码未匹配有效关注用户")

    device_info = build_device_network_info(binding_result)
    return DeviceBindResponse(
        id=binding_result.id,
        **device_info.model_dump(),
    )
