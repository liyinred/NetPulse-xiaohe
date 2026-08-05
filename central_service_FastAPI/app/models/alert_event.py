"""告警事件 ORM 模型。"""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertEvent(Base):
    """保存单次探测丢包产生的告警事件。"""

    __tablename__ = "alert_events"
    __table_args__ = (
        CheckConstraint(
            "protocol_type IN (1, 2, 3)",
            name="ck_alert_events_protocol_type",
        ),
        CheckConstraint(
            "probe_mode IN (1, 2)",
            name="ck_alert_events_probe_mode",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_ip_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ip_dict.id"),
        nullable=True,
    )
    target_ip_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("ip_dict.id"),
        nullable=True,
    )
    protocol_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    probe_mode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
