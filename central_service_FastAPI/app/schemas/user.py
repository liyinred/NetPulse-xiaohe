"""用户管理 API 数据模型。"""

from enum import IntEnum
from typing import Literal

from pydantic import BaseModel

from app.schemas.pagination import PaginatedData


class SubscribeStatus(IntEnum):
    """用户订阅状态筛选值。"""

    UNSUBSCRIBED = 0
    SUBSCRIBED = 1


class AlertType(IntEnum):
    """用户服务号告警类型值。"""

    NONE = 0
    CROSS_ISP = 1
    CROSS_PROVINCE = 2
    ALL = 3


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
    alertType: Literal[0, 1, 2, 3]
    createdTime: int | None


class UserListResponse(BaseModel):
    """用户管理分页列表统一响应。"""

    code: int = 200
    msg: str = "用户列表获取成功"
    data: PaginatedData[UserListItem]


class UserUpdateRequest(BaseModel):
    """修改用户等级和服务号告警类型的请求。"""

    userLevel: UserLevel
    alertType: Literal[0, 1, 2, 3]


class UserUpdateResponse(BaseModel):
    """修改用户信息的统一响应。"""

    code: int = 200
    msg: str = "用户信息更新成功"
    data: UserListItem
