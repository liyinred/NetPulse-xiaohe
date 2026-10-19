"""用户 ORM 模型。"""

from sqlalchemy import BigInteger, CheckConstraint, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """保存微信用户、订阅状态及告警设置。"""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "alert_type IN (0, 1, 2, 3)",
            name="ck_users_alert_type",
        ),
        CheckConstraint(
            "user_level IN (1, 2, 9)",
            name="ck_users_user_level",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    openid: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    scene_str: Mapped[str | None] = mapped_column(
        String(16), nullable=True, unique=True
    )
    subscribe_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alert_type: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    user_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    created_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_time: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
