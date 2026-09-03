"""临时 IP 按需探测 ORM 模型。"""

from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OnDemandExecution(Base):
    """保存可由多个用户查询共享的一次实际探测执行。"""

    __tablename__ = "on_demand_executions"
    __table_args__ = (
        CheckConstraint("ip_version IN (4, 6)", name="ck_on_demand_executions_ip_version"),
        CheckConstraint(
            "status IN (1, 2, 3, 4, 5)",
            name="ck_on_demand_executions_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    ip_version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_isp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_province: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class ProbeQuery(Base):
    """保存单个用户发起的临时 IP 查询及其访问期限。"""

    __tablename__ = "probe_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    execution_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("on_demand_executions.id"),
        nullable=False,
    )
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[int] = mapped_column(BigInteger, nullable=False)


class OnDemandNodeTask(Base):
    """保存一次按需执行分配给单个 Agent 的任务和结果。"""

    __tablename__ = "on_demand_node_tasks"
    __table_args__ = (
        CheckConstraint(
            "probe_modes IN (1, 2, 3)",
            name="ck_on_demand_node_tasks_probe_modes",
        ),
        CheckConstraint(
            "status IN (1, 2, 3, 4, 5)",
            name="ck_on_demand_node_tasks_status",
        ),
        UniqueConstraint(
            "execution_id",
            "probe_device_id",
            name="uq_on_demand_node_tasks_execution_device",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("on_demand_executions.id"),
        nullable=False,
    )
    probe_device_id: Mapped[int] = mapped_column(Integer, ForeignKey("devices.id"), nullable=False)
    source_ip_id: Mapped[int] = mapped_column(Integer, nullable=False)
    probe_modes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False)
    result_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    finished_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
