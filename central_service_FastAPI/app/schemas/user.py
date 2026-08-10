"""用户管理 API 数据模型。"""

from enum import IntEnum

from pydantic import BaseModel

from app.schemas.pagination import PaginatedData


class SubscribeStatus(IntEnum):
    """用户订阅状态筛选值。"""

    UNSUBSCRIBED = 0
    SUBSCRIBED = 1


class UserLevel(IntEnum):
    """用户等级筛选值。"""

    STANDARD = 1
    PREMIUM = 2
    ADMIN = 9


class UserListItem(BaseModel):
    """用户管理列表中的单条用户记录。"""

    id: int
    openid: str | None
    userLevel: int
    subscribeStatus: int | None
    createdTime: int | None


class UserListResponse(BaseModel):
    """用户管理分页列表统一响应。"""

    code: int = 200
    msg: str = "用户列表获取成功"
    data: PaginatedData[UserListItem]
