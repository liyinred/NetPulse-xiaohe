"""设备 ORM 模型。"""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Device(Base):
    """保存终端设备、绑定用户和按需探测状态。"""

    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            "on_demand_status IN (0, 1)",
            name="ck_devices_on_demand_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    on_demand_status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    last_seen_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
