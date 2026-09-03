"""双向 MTR 任务 ORM 模型。"""

from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BidirectionalMTRTask(Base):
    """保存用户创建的一次双向 MTR 主任务。"""

    __tablename__ = "bidirectional_mtr_tasks"
    __table_args__ = (CheckConstraint("status IN (1, 2, 3, 4, 5)", name="ck_bidirectional_mtr_tasks_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class BidirectionalMTRDirection(Base):
    """保存双向 MTR 的单方向租约、IP 引用和逐跳结果。"""

    __tablename__ = "bidirectional_mtr_directions"
    __table_args__ = (
        CheckConstraint("direction IN ('A_TO_B', 'B_TO_A')", name="ck_bidirectional_mtr_directions_direction"),
        CheckConstraint("status IN (1, 2, 3, 4, 5)", name="ck_bidirectional_mtr_directions_status"),
        UniqueConstraint("mtr_task_id", "direction", name="uq_bidirectional_mtr_task_direction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mtr_task_id: Mapped[int] = mapped_column(Integer, ForeignKey("bidirectional_mtr_tasks.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    source_ip_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_ip_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ip_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_data: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
