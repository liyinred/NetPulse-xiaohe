"""设备 API 数据模型。"""

from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, IPvAnyAddress

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


class DeviceBindingStatusRequest(BaseModel):
    """设备绑定状态查询请求。"""

    device_id: str = Field(min_length=1, max_length=64)
    source_ipv4: IPv4Address
    source_ipv6: IPv6Address | None = None


class DeviceBindingStatusResponse(BaseModel):
    """设备绑定状态查询结果。"""

    bound: bool
    device: DeviceNetworkInfo | None = None


class PublicIPAddressResponse(BaseModel):
    """中央服务观察到的公网 IP。"""

    public_ip: IPvAnyAddress


def build_device_network_info(
    binding_result: DeviceBindingResult,
) -> DeviceNetworkInfo:
    """将设备绑定服务结果转换为 API 网络信息。

    参数:
        binding_result: 设备绑定或刷新服务返回的数据。
    返回:
        可直接用于绑定状态响应的设备网络信息。
    """
    network_info = binding_result.network_info
    return DeviceNetworkInfo(
        device_id=binding_result.device_id,
        public_ipv4=network_info.public_ipv4,
        public_ipv6=binding_result.source_ipv6,
        isp=network_info.isp,
        province=network_info.province,
        city=network_info.city_name,
        isp_name=network_info.isp_name,
        province_name=network_info.province_name,
    )
