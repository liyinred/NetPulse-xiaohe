"""设备绑定服务。"""

from dataclasses import dataclass
from ipaddress import IPv4Address

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.device import Device
from app.models.user import User
from app.services.network import NetworkInfo, lookup_network


@dataclass(frozen=True)
class DeviceBindingResult:
    """保存设备绑定结果及中央服务识别的网络属性。"""

    id: int
    device_id: str
    network_info: NetworkInfo


async def bind_device_by_scene(
    device_id: str,
    scene_str: str,
    client_host: str | None,
) -> DeviceBindingResult | None:
    """按二维码场景值绑定设备并更新公网网络属性。

    参数:
        device_id: Agent 本地持久化的设备标识。
        scene_str: 微信二维码携带的场景值。
        client_host: FastAPI 识别的客户端连接源地址。
    返回:
        用户已扫码且关注时返回设备绑定结果，否则返回 None。
    """
    with SessionLocal() as session:
        user_id = session.scalar(
            select(User.id).where(
                User.scene_str == scene_str,
                User.openid.is_not(None),
                User.subscribe_status == 1,
            )
        )
    if user_id is None:
        return None

    public_ipv4 = parse_public_ipv4(client_host)
    network_info = await lookup_network(public_ipv4)

    with SessionLocal.begin() as session:
        current_user_id = session.scalar(
            select(User.id).where(
                User.id == user_id,
                User.scene_str == scene_str,
                User.openid.is_not(None),
                User.subscribe_status == 1,
            )
        )
        if current_user_id is None:
            return None

        device = session.scalar(
            select(Device).where(Device.device_id == device_id)
        )
        if device is None:
            device = Device(device_id=device_id)
            session.add(device)

        device.user_id = current_user_id
        device.public_ipv4 = str(network_info.public_ipv4)
        device.isp = network_info.isp
        device.province = network_info.province
        device.city = network_info.city_name
        session.flush()
        return DeviceBindingResult(
            id=device.id,
            device_id=device.device_id,
            network_info=network_info,
        )


def parse_public_ipv4(client_host: str | None) -> IPv4Address:
    """校验客户端连接源地址并返回公网 IPv4。

    参数:
        client_host: FastAPI 识别的客户端连接源地址。
    返回:
        校验通过的公网 IPv4 地址。
    """
    if client_host is None:
        raise ValueError("无法识别客户端地址")
    try:
        public_ipv4 = IPv4Address(client_host)
    except ValueError as exc:
        raise ValueError("客户端地址不是 IPv4") from exc
    if not public_ipv4.is_global:
        raise ValueError("客户端地址不是公网 IPv4")
    return public_ipv4
