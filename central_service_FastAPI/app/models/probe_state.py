"""持续探测状态 ORM 模型。"""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProbeStateMixin:
    """复用三种协议探测状态表的公共字段。"""

    time_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    source_ip_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ip_dict.id"),
        primary_key=True,
    )
    target_ip_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ip_dict.id"),
        primary_key=True,
    )
    probe_mode: Mapped[int] = mapped_column(Integer, primary_key=True)
    loss_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    rtt_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class ICMPProbeState(ProbeStateMixin, Base):
    """保存每个自然分钟窗口的 ICMP 探测状态。"""

    __tablename__ = "icmp_probe_state"
    __table_args__ = (
        CheckConstraint(
            "probe_mode IN (1, 2)",
            name="ck_icmp_probe_state_probe_mode",
        ),
        CheckConstraint(
            "loss_rate BETWEEN 0 AND 1000",
            name="ck_icmp_probe_state_loss_rate",
        ),
    )


class TCPProbeState(ProbeStateMixin, Base):
    """保存每个自然分钟窗口的 TCP 探测状态。"""

    __tablename__ = "tcp_probe_state"
    __table_args__ = (
        CheckConstraint(
            "probe_mode IN (1, 2)",
            name="ck_tcp_probe_state_probe_mode",
        ),
        CheckConstraint(
            "loss_rate BETWEEN 0 AND 1000",
            name="ck_tcp_probe_state_loss_rate",
        ),
    )


class UDPProbeState(ProbeStateMixin, Base):
    """保存每个自然分钟窗口的 UDP 探测状态。"""

    __tablename__ = "udp_probe_state"
    __table_args__ = (
        CheckConstraint(
            "probe_mode IN (1, 2)",
            name="ck_udp_probe_state_probe_mode",
        ),
        CheckConstraint(
            "loss_rate BETWEEN 0 AND 1000",
            name="ck_udp_probe_state_loss_rate",
        ),
    )
