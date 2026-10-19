"""设备 API 数据模型。"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.services.device import DeviceBindingResult


class DeviceBindRequest(BaseModel):
    """设备绑定请求。"""

    device_id: str = Field(min_length=1, max_length=64)
    scene_str: str = Field(min_length=16, max_length=16)
    source_ipv4: IPv4Address
    source_ipv6: IPv6Address | None = None


class DeviceNetworkInfo(BaseModel):
    """设备绑定成功后的网络信息。"""

    device_id: str
    public_ipv4: IPv4Address
    public_ipv6: IPv6Address | None
    isp: int
    province: int
    city: str
    isp_name: str
    province_name: str


class DeviceBindResponse(DeviceNetworkInfo):
    """设备绑定结果。"""

    id: int


class DeviceExistsResponse(BaseModel):
    """设备标识存在性查询结果。"""

    exists: bool


class PublicIPAddressResponse(BaseModel):
    """中央服务观察到的公网 IPv4。"""

    public_ip: IPv4Address


def build_device_network_info(
    binding_result: DeviceBindingResult,
) -> DeviceNetworkInfo:
    """将设备绑定服务结果转换为 API 网络信息。

    参数:
        binding_result: 设备绑定服务返回的数据。
    返回:
        可直接用于设备绑定响应的网络信息。
    """
    network_info = binding_result.network_info
    if not isinstance(network_info.public_ip, IPv4Address):
        raise ValueError("设备绑定网络信息缺少 IPv4 地址")
    return DeviceNetworkInfo(
        device_id=binding_result.device_id,
        public_ipv4=network_info.public_ip,
        public_ipv6=binding_result.source_ipv6,
        isp=network_info.isp,
        province=network_info.province,
        city=network_info.city_name,
        isp_name=network_info.isp_name,
        province_name=network_info.province_name,
    )
