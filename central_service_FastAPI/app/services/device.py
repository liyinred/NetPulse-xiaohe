"""设备绑定与网络地址持久化服务。"""

from dataclasses import dataclass
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from time import time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.device import Device
from app.models.ip_dict import IPDict
from app.models.user import User
from app.services.network import NetworkInfo, lookup_network
from app.services.wechat import QRCODE_EXPIRE_SECONDS


QRCODE_TIMESTAMP_FORMAT = "%y%m%d%H%M%S"


@dataclass(frozen=True)
class DeviceBindingResult:
    """保存设备绑定结果及中央服务识别的 IPv4 网络属性。"""

    id: int
    device_id: str
    network_info: NetworkInfo
    source_ipv6: IPv6Address | None


def _find_bound_user_id(session: Session, device_id: str) -> int | None:
    """查询设备当前绑定且仍关注服务号的用户。

    参数:
        session: 当前数据库会话。
        device_id: Agent 本地持久化的设备标识。
    返回:
        有效绑定用户的内部主键；不存在时返回 None。
    """
    return session.scalar(
        select(User.id)
        .join(Device, Device.user_id == User.id)
        .where(
            Device.device_id == device_id,
            User.openid.is_not(None),
            User.subscribe_status == 1,
        )
    )


def _find_scene_user_id(
    session: Session,
    scene_str: str,
    current_time: int,
) -> int | None:
    """查询二维码场景对应且仍在有效期内的关注用户。

    参数:
        session: 当前数据库会话。
        scene_str: 微信二维码携带的场景值。
        current_time: 当前 Unix 时间戳，单位秒。
    返回:
        有效场景用户的内部主键；不存在时返回 None。
    """
    try:
        scene_time = datetime.strptime(
            scene_str[:12],
            QRCODE_TIMESTAMP_FORMAT,
        ).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    except ValueError:
        return None
    scene_age = current_time - int(scene_time.timestamp())
    if scene_age < 0 or scene_age > QRCODE_EXPIRE_SECONDS:
        return None

    return session.scalar(
        select(User.id).where(
            User.scene_str == scene_str,
            User.openid.is_not(None),
            User.subscribe_status == 1,
        )
    )


def _upsert_ip_record(
    session: Session,
    device_id: int,
    public_ip: IPv4Address | IPv6Address,
    update_time: int,
    network_info: NetworkInfo | None = None,
) -> None:
    """创建或刷新设备关联的 IP 字典记录。

    参数:
        session: 当前数据库会话。
        device_id: devices 表内部主键。
        public_ip: 要保存的公网 IPv4 或 IPv6。
        update_time: 本次刷新 Unix 时间戳，单位秒。
        network_info: IPv4 归属查询结果；IPv6 暂无结果时允许为空。
    返回:
        无返回值；记录变更写入当前事务。
    """
    ip_record = session.scalar(select(IPDict).where(IPDict.ip == public_ip.packed))
    if ip_record is None:
        ip_record = IPDict(ip=public_ip.packed)
        session.add(ip_record)

    ip_record.device_related_id = device_id
    ip_record.ip_version = public_ip.version
    ip_record.update_time = update_time
    if network_info is not None:
        ip_record.isp = network_info.isp
        ip_record.province = network_info.province
        ip_record.city = network_info.city_name


def _persist_device_binding(
    session: Session,
    device_id: str,
    user_id: int,
    source_ipv4: IPv4Address,
    source_ipv6: IPv6Address | None,
    network_info: NetworkInfo,
    update_time: int,
) -> Device:
    """在同一事务中保存设备绑定和当前公网地址。

    参数:
        session: 当前数据库会话。
        device_id: Agent 本地持久化的设备标识。
        user_id: 绑定用户内部主键。
        source_ipv4: 当前公网 IPv4。
        source_ipv6: 当前公网 IPv6，未获取到时为空。
        network_info: IPv4 归属查询结果。
        update_time: 本次刷新 Unix 时间戳，单位秒。
    返回:
        新建或更新后的 Device ORM 对象。
    """
    device = session.scalar(select(Device).where(Device.device_id == device_id))
    if device is None:
        device = Device(
            device_id=device_id,
            created_time=update_time,
        )
        session.add(device)
        session.flush()

    device.user_id = user_id
    device.updated_time = update_time
    _upsert_ip_record(
        session,
        device.id,
        source_ipv4,
        update_time,
        network_info,
    )
    if source_ipv6 is not None:
        _upsert_ip_record(session, device.id, source_ipv6, update_time)
    return device


async def refresh_bound_device(
    device_id: str,
    source_ipv4: IPv4Address,
    source_ipv6: IPv6Address | None,
) -> DeviceBindingResult | None:
    """查询有效绑定并刷新设备当前公网地址。

    参数:
        device_id: Agent 本地持久化的设备标识。
        source_ipv4: 当前公网 IPv4。
        source_ipv6: 当前公网 IPv6，未获取到时为空。
    返回:
        已绑定时返回刷新结果，未绑定或用户未关注时返回 None。
    """
    with SessionLocal() as session:
        user_id = _find_bound_user_id(session, device_id)
    if user_id is None:
        return None

    network_info = await lookup_network(source_ipv4)
    update_time = int(time())
    with SessionLocal.begin() as session:
        current_user_id = _find_bound_user_id(session, device_id)
        if current_user_id != user_id:
            return None
        device = _persist_device_binding(
            session,
            device_id,
            current_user_id,
            source_ipv4,
            source_ipv6,
            network_info,
            update_time,
        )
        return DeviceBindingResult(
            id=device.id,
            device_id=device_id,
            network_info=network_info,
            source_ipv6=source_ipv6,
        )


async def bind_device_by_scene(
    device_id: str,
    scene_str: str,
    source_ipv4: IPv4Address,
    source_ipv6: IPv6Address | None,
) -> DeviceBindingResult | None:
    """按有效二维码场景绑定设备并保存当前公网地址。

    参数:
        device_id: Agent 本地持久化的设备标识。
        scene_str: 微信二维码携带的场景值。
        source_ipv4: 当前公网 IPv4。
        source_ipv6: 当前公网 IPv6，未获取到时为空。
    返回:
        用户已扫码且关注时返回设备绑定结果，否则返回 None。
    """
    current_time = int(time())
    with SessionLocal() as session:
        user_id = _find_scene_user_id(session, scene_str, current_time)
    if user_id is None:
        return None

    network_info = await lookup_network(source_ipv4)
    current_time = int(time())
    with SessionLocal.begin() as session:
        current_user_id = _find_scene_user_id(session, scene_str, current_time)
        if current_user_id != user_id:
            return None
        device = _persist_device_binding(
            session,
            device_id,
            current_user_id,
            source_ipv4,
            source_ipv6,
            network_info,
            current_time,
        )
        return DeviceBindingResult(
            id=device.id,
            device_id=device_id,
            network_info=network_info,
            source_ipv6=source_ipv6,
        )
