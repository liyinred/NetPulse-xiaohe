"""用户管理查询服务。"""

from time import time

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.pagination import PaginatedData, PaginationParams
from app.schemas.user import UserListItem
from app.services.pagination import paginate_query


USER_SORT_COLUMNS = {
    "id": User.id,
    "openid": User.openid,
    "userLevel": User.user_level,
    "subscribeStatus": User.subscribe_status,
    "alertType": User.alert_type,
    "createdTime": User.created_time,
    "updatedTime": User.updated_time,
}


def _build_user_list_item(user: User) -> UserListItem:
    """将 User ORM 记录转换为用户管理列表项。

    参数:
        user: 要转换的 User ORM 记录。
    返回:
        用户管理列表项。
    """
    return UserListItem(
        id=user.id,
        openid=user.openid,
        userLevel=user.user_level,
        subscribeStatus=user.subscribe_status,
        alertType=user.alert_type,
        createdTime=user.created_time,
        updatedTime=user.updated_time,
    )


def list_users(
    pagination: PaginationParams,
    openid: str | None = None,
    subscribe_status: int | None = None,
    user_level: int | None = None,
    alert_type: int | None = None,
) -> PaginatedData[UserListItem]:
    """按筛选条件查询 users 表并返回数据库分页结果。

    参数:
        pagination: 统一分页和排序参数。
        openid: openid 模糊筛选值。
        subscribe_status: 订阅状态精确筛选值。
        user_level: 用户等级精确筛选值。
        alert_type: 服务号告警类型精确筛选值。
    返回:
        用户列表记录、当前页、每页条数和总记录数。
    """
    statement = select(User)
    if openid:
        statement = statement.where(User.openid.contains(openid))
    if subscribe_status is not None:
        statement = statement.where(User.subscribe_status == subscribe_status)
    if user_level is not None:
        statement = statement.where(User.user_level == user_level)
    if alert_type is not None:
        statement = statement.where(User.alert_type == alert_type)

    with SessionLocal() as session:
        users, total = paginate_query(
            session,
            statement,
            pagination,
            USER_SORT_COLUMNS,
            "createdTime",
            User.id,
        )
        records = [_build_user_list_item(user) for user in users]
    return PaginatedData(
        records=records,
        current=pagination.current,
        size=pagination.size,
        total=total,
    )


def update_user(
    user_id: int,
    user_level: int,
    alert_type: int,
) -> UserListItem | None:
    """按用户 ID 修改用户等级和服务号告警类型。

    参数:
        user_id: users 表记录 ID。
        user_level: 新用户等级。
        alert_type: 新告警类型，0 表示不接收服务号告警。
    返回:
        更新后的用户管理列表项；用户不存在时返回 None。
    """
    with SessionLocal.begin() as session:
        user = session.get(User, user_id)
        if user is None:
            return None
        user.user_level = user_level
        user.alert_type = alert_type
        user.updated_time = int(time())
        session.flush()
        return _build_user_list_item(user)
