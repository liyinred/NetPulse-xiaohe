"""设备绑定路由。"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.device import Device
from app.models.user import User
from app.schemas.device import DeviceBindRequest, DeviceBindResponse


router = APIRouter(prefix="/devices", tags=["设备"])


@router.post("/bind", response_model=DeviceBindResponse)
def bind_device(binding: DeviceBindRequest) -> DeviceBindResponse:
    """将设备绑定到已关注的微信用户。

    参数:
        binding: 包含 device_id、openid 和公网 IPv4 的绑定信息。
    返回:
        新建或更新后的设备标识与公网 IPv4。
    """
    with SessionLocal.begin() as session:
        user = session.scalar(select(User).where(User.openid == binding.openid))
        if user is None:
            raise HTTPException(status_code=404, detail="openid 对应的用户不存在")
        if user.subscribe_status != 1:
            raise HTTPException(status_code=409, detail="用户未关注服务号")

        device = session.scalar(
            select(Device).where(Device.device_id == binding.device_id)
        )
        if device is None:
            device = Device(device_id=binding.device_id)
            session.add(device)

        device.user_id = user.id
        device.public_ipv4 = str(binding.public_ipv4)
        session.flush()
        return DeviceBindResponse(
            id=device.id,
            device_id=device.device_id,
            public_ipv4=binding.public_ipv4,
        )
