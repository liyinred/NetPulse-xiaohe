"""设备 API 数据模型。"""

from ipaddress import IPv4Address

from pydantic import BaseModel, Field


class DeviceBindRequest(BaseModel):
    """设备绑定请求。"""

    device_id: str = Field(min_length=1, max_length=64)
    openid: str = Field(min_length=1, max_length=128)
    public_ipv4: IPv4Address


class DeviceBindResponse(BaseModel):
    """设备绑定结果。"""

    id: int
    device_id: str
    public_ipv4: IPv4Address
