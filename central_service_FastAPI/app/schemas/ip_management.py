"""IP 管理 API 数据模型。"""

from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, IPvAnyAddress

from app.schemas.pagination import PaginatedData


class IPVersion(IntEnum):
    """IP 版本筛选值。"""

    IPV4 = 4
    IPV6 = 6


class ISPCode(IntEnum):
    """运营商筛选编码。"""

    TELECOM = 1
    MOBILE = 2
    UNICOM = 3
    OTHER = 4


class PublicStatus(IntEnum):
    """IP 公开状态筛选值。"""

    PRIVATE = 0
    PUBLIC = 1


class IPListItem(BaseModel):
    """IP 管理列表中的单条 IP 记录。"""

    id: int
    ip: str
    ipVersion: int
    publicStatus: Literal[0, 1]
    isp: int | None
    ispName: str
    province: int | None
    provinceName: str
    city: str | None
    updateTime: int


class IPListResponse(BaseModel):
    """IP 管理分页列表统一响应。"""

    code: int = 200
    msg: str = "IP 列表获取成功"
    data: PaginatedData[IPListItem]


class IPUpsertRequest(BaseModel):
    """新增或刷新 IP 记录的请求。"""

    ip: IPvAnyAddress
    publicStatus: Literal[0, 1] = 1


class IPUpsertResponse(BaseModel):
    """新增或刷新 IP 记录的统一响应。"""

    code: int = 200
    msg: str = "IP 信息保存成功"
    data: IPListItem


class IPPublicStatusUpdateRequest(BaseModel):
    """修改 IP 公开状态的请求。"""

    publicStatus: Literal[0, 1]


class IPPublicStatusUpdateResponse(BaseModel):
    """修改 IP 公开状态的统一响应。"""

    code: int = 200
    msg: str = "IP 公开状态更新成功"
    data: IPListItem
