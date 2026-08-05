"""IP 字典 ORM 模型。"""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IPDict(Base):
    """保存探测 IP、网络属性及关联设备。"""

    __tablename__ = "ip_dict"
    __table_args__ = (
        CheckConstraint(
            "ip_version IN (4, 6)",
            name="ck_ip_dict_ip_version",
        ),
        CheckConstraint(
            "public_status IN (0, 1)",
            name="ck_ip_dict_public_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_related_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("devices.id"),
        nullable=True,
    )
    ip: Mapped[str] = mapped_column(String(45), nullable=False, unique=True)
    ip_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=4, server_default=text("4")
    )
    isp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    province: Mapped[int | None] = mapped_column(Integer, nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    public_status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    update_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
