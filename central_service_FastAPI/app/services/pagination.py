"""SQLAlchemy 通用数据库分页逻辑。"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.schemas.pagination import PaginationParams


def paginate_query(
    session: Session,
    statement: Select[Any],
    pagination: PaginationParams,
    sort_columns: Mapping[str, ColumnElement[Any]],
    default_sort_field: str,
    unique_column: ColumnElement[Any],
) -> tuple[list[Any], int]:
    """对 SQLAlchemy 查询执行稳定排序和数据库分页。

    参数:
        session: 当前数据库会话。
        statement: 尚未分页的 SQLAlchemy Select 查询。
        pagination: 统一分页和排序参数。
        sort_columns: 前端排序字段到数据库列的白名单映射。
        default_sort_field: 未显式排序时使用的字段名。
        unique_column: 追加到排序末尾的唯一键列。
    返回:
        当前页记录列表和满足条件的总记录数。
    """
    sort_field = pagination.sort_field or default_sort_field
    sort_column = sort_columns.get(sort_field)
    if sort_column is None:
        raise ValueError(f"不支持的排序字段: {sort_field}")

    sort_order = pagination.sort_order or "desc"
    order_method = "asc" if sort_order == "asc" else "desc"
    order_clauses = [getattr(sort_column, order_method)()]
    if sort_column is not unique_column:
        order_clauses.append(getattr(unique_column, order_method)())

    total_statement = select(func.count()).select_from(
        statement.order_by(None).subquery()
    )
    total = session.scalar(total_statement) or 0
    offset = (pagination.current - 1) * pagination.size
    records = session.scalars(
        statement.order_by(*order_clauses).offset(offset).limit(pagination.size)
    ).all()
    return list(records), total
