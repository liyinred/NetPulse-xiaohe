"""持续探测状态 ORM 模型。"""

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _source_time_index(table_name: str) -> Index:
    """构建按源节点、探测模式和时间范围查询的覆盖索引。

    参数:
        table_name: 探测状态表名称。
    返回:
        覆盖趋势和报告查询所需列的复合索引。
    """
    return Index(
        f"ix_{table_name}_source_mode_time",
        "source_ip_id",
        "probe_mode",
        "time_id",
        "target_ip_id",
        "loss_rate",
        "rtt_ms",
        "device_related_id",
    )


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
        _source_time_index("probe_state_icmp"),
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
        _source_time_index("probe_state_tcp"),
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
        _source_time_index("probe_state_udp"),
    )
