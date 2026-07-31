"""用户 ORM 模型。"""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.device import Device


class User(TimestampMixin, Base):
    """保存微信用户及扫码绑定状态。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    openid: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    scene_str: Mapped[str | None] = mapped_column(
        String(16), nullable=True, unique=True
    )
    subscribe_status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    devices: Mapped[list["Device"]] = relationship(back_populates="user")
