"""补充 MTR 展示信息，保持 Agent 原始结果和幂等校验不变。"""

import asyncio
from collections import OrderedDict
from ipaddress import ip_address, ip_network
from time import monotonic

from app.schemas.bidirectional_mtr import MTRTaskResult
from app.services.network import IPLookupError, lookup_network


PRIVATE_NETWORKS = tuple(ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
))
SHARED_NETWORK = ip_network("100.64.0.0/10")
LOCATION_CACHE_LIMIT = 4096
LOCATION_CACHE: OrderedDict[str, tuple[float, str | None]] = OrderedDict()


def classify_mtr_address(value: str | None) -> str:
    """分类跳点地址，避免把所有非公网地址视作局域网。

    参数:
        value: 跳点 IP 或无响应时的空值。
    返回:
        公网、私网、共享、链路本地、回环、特殊或未知类型。
    """
    try:
        address = ip_address(value or "")
    except ValueError:
        return "unknown"
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_loopback:
        return "loopback"
    if address.is_link_local:
        return "link_local"
    if address in SHARED_NETWORK:
        return "shared"
    if any(address in network for network in PRIVATE_NETWORKS):
        return "private"
    return "public" if address.is_global and not address.is_multicast else "special"


async def lookup_mtr_location(value: str) -> str | None:
    """复用归属接口查询跳点位置，并缓存成功和失败结果。

    参数:
        value: 已分类的公网 IP。
    返回:
        位置文本；接口失败或超时返回空值。
    """
    now = monotonic()
    cached = LOCATION_CACHE.get(value)
    if cached is not None and cached[0] > now:
        LOCATION_CACHE.move_to_end(value)
        return cached[1]
    try:
        info = await asyncio.wait_for(lookup_network(ip_address(value), strict_province=False), timeout=2.5)
        location = " · ".join(dict.fromkeys(part for part in (info.province_name, info.city_name) if part)) or None
    except (IPLookupError, TimeoutError):
        location = None
    LOCATION_CACHE[value] = (monotonic() + (3600 if location else 60), location)
    LOCATION_CACHE.move_to_end(value)
    while len(LOCATION_CACHE) > LOCATION_CACHE_LIMIT:
        LOCATION_CACHE.popitem(last=False)
    return location


async def enrich_mtr_result(result: MTRTaskResult) -> None:
    """按去重公网 IP 并发补充展示信息，不修改数据库原始结果。

    参数:
        result: 当前用户已授权访问的 MTR 响应对象。
    返回:
        无；原地更新响应中的网络类型和地理位置。
    """
    hops = [hop for direction in result.directions for hop in direction.hops]
    for hop in hops:
        hop.networkType = classify_mtr_address(hop.address)
        if hop.networkType != "public":
            hop.asns = []
    addresses = list(dict.fromkeys(hop.address for hop in hops if hop.networkType == "public" and hop.address))
    locations = dict(zip(addresses, await asyncio.gather(*(lookup_mtr_location(value) for value in addresses))))
    for hop in hops:
        hop.location = locations.get(hop.address)
