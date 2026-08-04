"""设备绑定路由。"""

from fastapi import APIRouter, HTTPException, Request

from app.schemas.device import DeviceBindRequest, DeviceBindResponse
from app.services.device import bind_device_by_scene
from app.services.network import IPLookupError


router = APIRouter(prefix="/devices", tags=["设备"])


@router.post("/bind", response_model=DeviceBindResponse)
async def bind_device(binding: DeviceBindRequest, request: Request) -> DeviceBindResponse:
    """使用二维码场景值绑定设备并返回服务端识别的网络属性。

    参数:
        binding: 包含设备标识和二维码场景值的绑定信息。
        request: 用于读取客户端连接源地址的 FastAPI Request。
    返回:
        新建或更新后的设备标识、公网 IPv4 及归一化网络属性。
    """
    try:
        binding_result = await bind_device_by_scene(
            binding.device_id,
            binding.scene_str,
            request.client.host if request.client is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IPLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if binding_result is None:
        raise HTTPException(status_code=404, detail="二维码未匹配有效关注用户")

    network_info = binding_result.network_info
    return DeviceBindResponse(
        id=binding_result.id,
        device_id=binding_result.device_id,
        public_ipv4=network_info.public_ipv4,
        isp=network_info.isp,
        province=network_info.province,
        city=network_info.city_name,
        isp_name=network_info.isp_name,
        province_name=network_info.province_name,
    )
