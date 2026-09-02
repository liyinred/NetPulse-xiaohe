"""持续探测状态 ORM 模型。"""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProbeStateMixin:
    """复用三种协议探测状态表的公共字段。"""

    time_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    device_related_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("devices.id"),
        nullable=False,
    )
    source_ip_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    target_ip_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    probe_mode: Mapped[int] = mapped_column(Integer, primary_key=True)
    loss_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    rtt_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class ICMPProbeState(ProbeStateMixin, Base):
    """保存每个自然分钟窗口的 ICMP 探测状态。"""

    __tablename__ = "probe_state_icmp"
    __table_args__ = (
        CheckConstraint(
            "probe_mode IN (1, 2)",
            name="ck_probe_state_icmp_probe_mode",
        ),
        CheckConstraint(
            "loss_rate BETWEEN 0 AND 1000",
            name="ck_probe_state_icmp_loss_rate",
        ),
        CheckConstraint(
            "rtt_ms BETWEEN 0 AND 300",
            name="ck_probe_state_icmp_rtt_ms",
        ),
    )


class TCPProbeState(ProbeStateMixin, Base):
    """保存每个自然分钟窗口的 TCP 探测状态。"""

    __tablename__ = "probe_state_tcp"
    __table_args__ = (
        CheckConstraint(
            "probe_mode IN (1, 2)",
            name="ck_probe_state_tcp_probe_mode",
        ),
        CheckConstraint(
            "loss_rate BETWEEN 0 AND 1000",
            name="ck_probe_state_tcp_loss_rate",
        ),
        CheckConstraint(
            "rtt_ms BETWEEN 0 AND 300",
            name="ck_probe_state_tcp_rtt_ms",
        ),
    )


class UDPProbeState(ProbeStateMixin, Base):
    """保存每个自然分钟窗口的 UDP 探测状态。"""

    __tablename__ = "probe_state_udp"
    __table_args__ = (
        CheckConstraint(
            "probe_mode IN (1, 2)",
            name="ck_probe_state_udp_probe_mode",
        ),
        CheckConstraint(
            "loss_rate BETWEEN 0 AND 1000",
            name="ck_probe_state_udp_loss_rate",
        ),
        CheckConstraint(
            "rtt_ms BETWEEN 0 AND 300",
            name="ck_probe_state_udp_rtt_ms",
        ),
    )
