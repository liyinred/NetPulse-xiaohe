"""通用分页 API 数据模型。"""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


RecordType = TypeVar("RecordType")


class PaginationParams(BaseModel):
    """统一分页和排序查询参数。"""

    model_config = ConfigDict(populate_by_name=True)

    current: int = Field(default=1, ge=1)
    size: int = Field(default=25, ge=1, le=100)
    sort_field: str | None = Field(default=None, alias="sortField")
    sort_order: Literal["asc", "desc"] | None = Field(
        default=None,
        alias="sortOrder",
    )


class PaginatedData(BaseModel, Generic[RecordType]):
    """统一分页响应数据。"""

    records: list[RecordType]
    current: int
    size: int
    total: int
