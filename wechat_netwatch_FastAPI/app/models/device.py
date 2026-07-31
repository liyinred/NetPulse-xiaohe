"""设备 ORM 模型。"""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class Device(TimestampMixin, Base):
    """保存终端设备、绑定用户和当前网络属性。"""

    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("device_id", name="uq_devices_device_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    public_ipv4: Mapped[str | None] = mapped_column(String(15), nullable=True)
    isp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    province: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    user: Mapped["User | None"] = relationship(back_populates="devices")
