"""持续探测告警的跨分钟状态。"""

from sqlalchemy import BigInteger, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProbeAlertState(Base):
    """按源 IP、目标 IP、分类和协议保存故障确认及提醒状态。"""

    __tablename__ = "probe_alert_states"

    source_ip_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_ip_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    probe_mode: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol_type: Mapped[int] = mapped_column(Integer, primary_key=True)
    is_firing: Mapped[bool] = mapped_column(Boolean, nullable=False)
    abnormal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    normal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fault_started_at: Mapped[int | None] = mapped_column(BigInteger)
    last_notified_at: Mapped[int | None] = mapped_column(BigInteger)
    last_window_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
