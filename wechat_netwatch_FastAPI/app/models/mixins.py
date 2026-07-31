"""ORM 模型共享字段。"""

from sqlalchemy import BigInteger, text
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """为 ORM 模型提供 Unix 秒级创建和更新时间。"""

    created_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("(UNIX_TIMESTAMP())"),
    )
    updated_at: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("(UNIX_TIMESTAMP())"),
        onupdate=text("UNIX_TIMESTAMP()"),
    )
