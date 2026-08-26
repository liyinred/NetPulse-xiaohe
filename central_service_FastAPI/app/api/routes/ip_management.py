"""IP 管理路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.models.user import User
from app.schemas.ip_management import (
    IPListResponse,
    IPVersion,
    ISPCode,
    IPPublicStatusUpdateRequest,
    IPPublicStatusUpdateResponse,
    PublicStatus,
    IPUpsertRequest,
    IPUpsertResponse,
)
from app.schemas.pagination import PaginationParams
from app.services.auth import get_current_admin
from app.services.ip_management import (
    list_ips,
    update_ip_public_status,
    upsert_ip_record,
)
from app.services.network import IPLookupError


router = APIRouter(prefix="/api/ip", tags=["IP 管理"])


@router.post("", response_model=IPUpsertResponse)
async def upsert_ip(
    request: IPUpsertRequest,
    _: Annotated[User, Depends(get_current_admin)],
) -> IPUpsertResponse:
    """查询 IP 归属信息并新增或刷新 ip_dict 记录。

    参数:
        request: 包含标准 IPv4 或 IPv6 地址的请求。
        _: 管理员认证依赖解析出的当前用户。
    返回:
        统一响应包装的新增或刷新后 IP 数据。
    """
    try:
        data = await upsert_ip_record(request.ip, request.publicStatus)
    except IPLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return IPUpsertResponse(data=data)


@router.put(
    "/{ip_id}/public-status",
    response_model=IPPublicStatusUpdateResponse,
)
def update_public_status(
    request: IPPublicStatusUpdateRequest,
    _: Annotated[User, Depends(get_current_admin)],
    ip_id: int = Path(ge=1),
) -> IPPublicStatusUpdateResponse:
    """按记录 ID 修改 IP 公开状态。

    参数:
        request: 包含新公开状态的请求。
        _: 管理员认证依赖解析出的当前用户。
        ip_id: ip_dict 表记录 ID。
    返回:
        统一响应包装的更新后 IP 数据。
    """
    data = update_ip_public_status(ip_id, request.publicStatus)
    if data is None:
        raise HTTPException(status_code=404, detail="IP 记录不存在")
    return IPPublicStatusUpdateResponse(data=data)


@router.get("/list", response_model=IPListResponse)
def get_ip_list(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(get_current_admin)],
    ip: str | None = Query(default=None, max_length=45),
    ip_version: IPVersion | None = Query(default=None, alias="ipVersion"),
    isp: ISPCode | None = Query(default=None),
    province: int | None = Query(default=None, ge=1, le=35),
    city: str | None = Query(default=None, max_length=64),
    public_status: PublicStatus | None = Query(
        default=None,
        alias="publicStatus",
    ),
) -> IPListResponse:
    """查询 ip_dict 表的筛选、排序和分页列表。

    参数:
        pagination: current、size、sortField、sortOrder 分页协议。
        _: 管理员认证依赖解析出的当前用户。
        ip: IP 地址模糊筛选值。
        ip_version: IP 版本精确筛选值。
        isp: 运营商编码精确筛选值。
        province: 省份编码精确筛选值。
        city: 城市名称模糊筛选值。
        public_status: 公开状态精确筛选值。
    返回:
        统一响应包装的 IP 分页数据。
    """
    try:
        data = list_ips(
            pagination,
            ip=ip,
            ip_version=ip_version,
            isp=isp,
            province=province,
            city=city,
            public_status=public_status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return IPListResponse(data=data)
