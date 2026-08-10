"""用户管理查询服务。"""

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
    "createdTime": User.created_time,
}


def list_users(
    pagination: PaginationParams,
    openid: str | None = None,
    subscribe_status: int | None = None,
    user_level: int | None = None,
) -> PaginatedData[UserListItem]:
    """按筛选条件查询 users 表并返回数据库分页结果。

    参数:
        pagination: 统一分页和排序参数。
        openid: openid 模糊筛选值。
        subscribe_status: 订阅状态精确筛选值。
        user_level: 用户等级精确筛选值。
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

    with SessionLocal() as session:
        users, total = paginate_query(
            session,
            statement,
            pagination,
            USER_SORT_COLUMNS,
            "createdTime",
            User.id,
        )
        records = [
            UserListItem(
                id=user.id,
                openid=user.openid,
                userLevel=user.user_level,
                subscribeStatus=user.subscribe_status,
                createdTime=user.created_time,
            )
            for user in users
        ]
    return PaginatedData(
        records=records,
        current=pagination.current,
        size=pagination.size,
        total=total,
    )
