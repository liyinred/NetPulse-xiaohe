"""用户管理路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response

from app.models.user import User
from app.schemas.cdk import CdkCurrentData, CdkCurrentResponse
from app.schemas.pagination import PaginationParams
from app.schemas.user import (
    AlertType,
    SubscribeStatus,
    UserLevel,
    UserListResponse,
    UserUpdateRequest,
    UserUpdateResponse,
)
from app.services.auth import get_current_admin
from app.services.cdk import get_cdk_snapshot
from app.services.user import list_users, update_user


router = APIRouter(prefix="/api/user", tags=["用户管理"])


@router.get("/list", response_model=UserListResponse)
def get_user_list(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(get_current_admin)],
    openid: str | None = Query(default=None, max_length=128),
    subscribe_status: SubscribeStatus | None = Query(
        default=None,
        alias="subscribeStatus",
    ),
    user_level: UserLevel | None = Query(
        default=None,
        alias="userLevel",
    ),
    alert_type: AlertType | None = Query(
        default=None,
        alias="alertType",
    ),
) -> UserListResponse:
    """查询 users 表的筛选、排序和分页列表。

    参数:
        pagination: current、size、sortField、sortOrder 分页协议。
        _: 管理员认证依赖解析出的当前用户。
        openid: openid 模糊筛选值。
        subscribe_status: 订阅状态精确筛选值。
        user_level: 用户等级精确筛选值。
        alert_type: 服务号告警类型精确筛选值。
    返回:
        统一响应包装的用户分页数据。
    """
    try:
        data = list_users(
            pagination,
            openid=openid,
            subscribe_status=subscribe_status,
            user_level=user_level,
            alert_type=alert_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return UserListResponse(data=data)


@router.get("/cdk/current", response_model=CdkCurrentResponse)
def get_current_cdk(
    response: Response,
    _: Annotated[User, Depends(get_current_admin)],
) -> CdkCurrentResponse:
    """获取当前有效的 CDK 及其剩余时间。

    参数:
        response: FastAPI 响应对象，用于设置禁用缓存响应头。
        _: 管理员认证依赖解析出的当前用户。
    返回:
        统一响应包装的当前 CDK 数据。
    """
    response.headers["Cache-Control"] = "no-store"
    snapshot = get_cdk_snapshot()
    return CdkCurrentResponse(
        data=CdkCurrentData(
            code=snapshot.code,
            createdTime=snapshot.created_time,
            expireTime=snapshot.expire_time,
            serverTime=snapshot.server_time,
            expireSeconds=max(0, snapshot.expire_time - snapshot.server_time),
        )
    )


@router.put(
    "/{user_id}",
    response_model=UserUpdateResponse,
)
def update_user_info(
    request: UserUpdateRequest,
    _: Annotated[User, Depends(get_current_admin)],
    user_id: int = Path(ge=1),
) -> UserUpdateResponse:
    """按用户 ID 修改用户等级和服务号告警类型。

    参数:
        request: 包含新用户等级和告警类型的请求。
        _: 管理员认证依赖解析出的当前用户。
        user_id: users 表记录 ID。
    返回:
        统一响应包装的更新后用户数据。
    """
    data = update_user(user_id, request.userLevel, request.alertType)
    if data is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserUpdateResponse(data=data)
