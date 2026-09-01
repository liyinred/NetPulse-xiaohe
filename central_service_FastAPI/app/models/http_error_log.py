"""HTTP 5xx 错误日志 SQLite ORM 模型。"""

from sqlalchemy import Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class HttpErrorLogBase(DeclarativeBase):
    """HTTP 错误日志 SQLite 数据库的声明式基类。"""


class HttpErrorLog(HttpErrorLogBase):
    """保存 inbound 与 outbound HTTP 5xx 错误。"""

    __tablename__ = "http_error_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    error_type: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_time: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
