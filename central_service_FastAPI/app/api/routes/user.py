"""用户管理路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from app.models.user import User
from app.schemas.pagination import PaginationParams
from app.schemas.user import (
    AlertType,
    SubscribeStatus,
    UserAlertTypeUpdateRequest,
    UserAlertTypeUpdateResponse,
    UserLevel,
    UserListResponse,
)
from app.services.auth import get_current_user
from app.services.user import list_users, update_user_alert_type


router = APIRouter(prefix="/api/user", tags=["用户管理"])


@router.get("/list", response_model=UserListResponse)
def get_user_list(
    pagination: Annotated[PaginationParams, Depends()],
    _: Annotated[User, Depends(get_current_user)],
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
        _: JWT 认证解析出的当前用户。
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


@router.put(
    "/{user_id}/alert-type",
    response_model=UserAlertTypeUpdateResponse,
)
def update_alert_type(
    request: UserAlertTypeUpdateRequest,
    _: Annotated[User, Depends(get_current_user)],
    user_id: int = Path(ge=1),
) -> UserAlertTypeUpdateResponse:
    """按用户 ID 修改服务号告警类型。

    参数:
        request: 包含新告警类型的请求。
        _: JWT 认证解析出的当前用户。
        user_id: users 表记录 ID。
    返回:
        统一响应包装的更新后用户数据。
    """
    data = update_user_alert_type(user_id, request.alertType)
    if data is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserAlertTypeUpdateResponse(data=data)
