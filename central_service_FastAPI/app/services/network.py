"""公网 IPv4 归属信息查询服务。"""

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, IPv6Address, ip_address
from typing import Any

import httpx

from app.core.config import IP_LOOKUP_API_KEY


IP_LOOKUP_ENDPOINT = "http://43.138.198.101:8000/ip/api/apix"
IP_LOOKUP_TIMEOUT_SECONDS = 8.0

PROVINCE_CODES = {
    "北京": 2,
    "福建": 3,
    "甘肃": 4,
    "广东": 5,
    "广西": 6,
    "贵州": 7,
    "海南": 8,
    "河北": 9,
    "河南": 10,
    "黑龙江": 11,
    "湖北": 12,
    "湖南": 13,
    "吉林": 14,
    "江苏": 15,
    "江西": 16,
    "辽宁": 17,
    "内蒙古": 18,
    "宁夏": 19,
    "青海": 20,
    "山东": 21,
    "山西": 22,
    "陕西": 23,
    "上海": 24,
    "四川": 25,
    "天津": 26,
    "西藏": 27,
    "新疆": 28,
    "云南": 29,
    "浙江": 30,
    "重庆": 31,
    "安徽": 32,
    "香港": 33,
    "台湾": 34,
    "澳门": 35,
}
INVALID_NETWORK_VALUES = {"", "-", "n/a", "none", "null", "unknown", "未知"}


class IPLookupError(RuntimeError):
    """表示 IP 归属查询请求或响应无效。"""


@dataclass(frozen=True)
class NetworkInfo:
    """保存公网 IPv4 及归一化后的省份、城市、运营商信息。"""

    public_ipv4: IPv4Address
    isp: int
    province: int
    isp_name: str
    province_name: str
    city_name: str


def parse_public_address(
    client_host: str | None,
    expected_version: int,
) -> IPv4Address | IPv6Address:
    """解析中央服务观察到的指定版本公网地址。

    参数:
        client_host: FastAPI 识别的客户端连接源地址。
        expected_version: 期望的 IP 版本，仅支持 4 或 6。
    返回:
        版本匹配且可公开路由的 IP 地址。
    """
    if client_host is None:
        raise ValueError("无法识别客户端地址")
    try:
        public_ip = ip_address(client_host)
    except ValueError as exc:
        raise ValueError("客户端地址不是有效 IP") from exc

    if isinstance(public_ip, IPv6Address) and public_ip.ipv4_mapped is not None:
        public_ip = public_ip.ipv4_mapped
    if public_ip.version != expected_version:
        raise ValueError(f"客户端连接不是公网 IPv{expected_version}")
    if not public_ip.is_global:
        raise ValueError(f"客户端地址不是公网 IPv{expected_version}")
    return public_ip


async def lookup_network(public_ipv4: IPv4Address) -> NetworkInfo:
    """查询公网 IPv4 所在网段的省份、城市和运营商。

    参数:
        public_ipv4: 中央服务从连接中识别的公网 IPv4。
    返回:
        包含公网 IPv4、省份、城市、运营商展示名称和归一化编码的网络信息。
    """
    cidr = IPv4Network(f"{public_ipv4}/24", strict=False)
    try:
        async with httpx.AsyncClient(timeout=IP_LOOKUP_TIMEOUT_SECONDS) as client:
            response = await client.post(
                IP_LOOKUP_ENDPOINT,
                json={"apikey": IP_LOOKUP_API_KEY, "ranges": str(cidr)},
            )
            response.raise_for_status()
            payload: Any = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise IPLookupError(f"IP 归属查询请求失败: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), str):
        raise IPLookupError("IP 归属查询响应缺少 data 字段")
    province_name, city_name, isp_name = parse_ip_lookup_data(
        payload["data"], public_ipv4
    )
    province_name = validate_network_value(province_name, "省份")
    city_name = validate_network_value(city_name, "城市")
    isp_name = validate_network_value(isp_name, "运营商")
    province = normalize_province(province_name)
    if province == 1:
        raise IPLookupError("IP 归属查询未返回可识别的省份")
    return NetworkInfo(
        public_ipv4=public_ipv4,
        isp=normalize_isp(isp_name),
        province=province,
        isp_name=isp_name,
        province_name=province_name,
        city_name=city_name,
    )


def parse_ip_lookup_data(
    data: str,
    public_ipv4: IPv4Address,
) -> tuple[str, str, str]:
    """解析接口数据并查找覆盖指定公网 IPv4 的记录。

    参数:
        data: 接口返回的分号、逗号分隔数据。
        public_ipv4: 用于匹配网段记录的公网 IPv4。
    返回:
        省份名称、城市名称和运营商名称。
    """
    for record in data.split(";"):
        fields = [field.strip() for field in record.strip().split(",")]
        if len(fields) != 5:
            continue
        try:
            start_ip = IPv4Address(fields[0])
            end_ip = IPv4Address(fields[1])
        except ValueError:
            continue
        if start_ip <= public_ipv4 <= end_ip:
            province_name, separator, city_name = fields[2].partition("-")
            return (
                province_name.strip(),
                city_name.strip() if separator else "",
                fields[3],
            )
    raise IPLookupError("IP 归属查询响应未包含客户端地址")


def validate_network_value(value: str, field_name: str) -> str:
    """校验 IP 归属字段包含可用于绑定和展示的信息。

    参数:
        value: 接口返回的归属字段值。
        field_name: 用于错误信息的字段名称。
    返回:
        去除首尾空白后的有效字段值。
    """
    normalized = value.strip()
    if normalized.lower() in INVALID_NETWORK_VALUES:
        raise IPLookupError(f"IP 归属查询未返回有效{field_name}")
    return normalized


def normalize_isp(isp: str) -> int:
    """将运营商名称转换为设备表使用的编码。

    参数:
        isp: 接口返回的运营商名称。
    返回:
        电信为 1、移动为 2、联通为 3，其他为 4。
    """
    if "电信" in isp:
        return 1
    if "移动" in isp:
        return 2
    if "联通" in isp:
        return 3
    return 4


def normalize_province(province: str) -> int:
    """将省份名称转换为设备表使用的编码。

    参数:
        province: 接口返回的省份名称或简称。
    返回:
        已知省份对应 2 至 35，空值或未知省份返回 1。
    """
    normalized = province.strip().removeprefix("中国")
    for suffix in (
        "壮族自治区",
        "回族自治区",
        "维吾尔自治区",
        "特别行政区",
        "自治区",
        "省",
        "市",
    ):
        normalized = normalized.removesuffix(suffix)
    return PROVINCE_CODES.get(normalized, 1)
