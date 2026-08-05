"""公网 IP 地址发现路由。"""

from ipaddress import IPv4Address, IPv6Address

from fastapi import APIRouter, HTTPException, Request

from app.schemas.device import PublicIPAddressResponse
from app.services.network import parse_public_address


router = APIRouter(prefix="/network", tags=["网络"])


def _client_host(request: Request) -> str | None:
    """读取 FastAPI 连接信息中的客户端地址。

    参数:
        request: 当前 FastAPI Request。
    返回:
        可用的客户端地址字符串；连接信息不存在时返回 None。
    """
    return request.client.host if request.client is not None else None


@router.get("/public-ipv4", response_model=PublicIPAddressResponse)
async def get_public_ipv4(request: Request) -> PublicIPAddressResponse:
    """返回中央服务从 IPv4 连接观察到的公网地址。

    参数:
        request: 当前 FastAPI Request。
    返回:
        客户端公网 IPv4。
    """
    try:
        public_ip = parse_public_address(_client_host(request), 4)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not isinstance(public_ip, IPv4Address):
        raise HTTPException(status_code=400, detail="客户端连接不是公网 IPv4")
    return PublicIPAddressResponse(public_ip=public_ip)


@router.get("/public-ipv6", response_model=PublicIPAddressResponse)
async def get_public_ipv6(request: Request) -> PublicIPAddressResponse:
    """返回中央服务从 IPv6 连接观察到的公网地址。

    参数:
        request: 当前 FastAPI Request。
    返回:
        客户端公网 IPv6。
    """
    try:
        public_ip = parse_public_address(_client_host(request), 6)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not isinstance(public_ip, IPv6Address):
        raise HTTPException(status_code=400, detail="客户端连接不是公网 IPv6")
    return PublicIPAddressResponse(public_ip=public_ip)
