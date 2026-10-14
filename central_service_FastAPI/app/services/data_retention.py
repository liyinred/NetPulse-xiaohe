"""探测结果及告警记录的定时保留清理服务。"""

import asyncio
import logging
from datetime import datetime, timedelta
from time import time

from sqlalchemy import delete
from sqlalchemy.orm import InstrumentedAttribute

from app.core.retention import BEIJING_TIMEZONE, get_retention_cutoff
from app.db.session import SessionLocal
from app.models.alert_event import AlertEvent
from app.services.probe import PROBE_STATE_MODELS


logger = logging.getLogger(__name__)

PROBE_RETENTION_DAYS = 60
PROBE_RETENTION_RUN_HOURS = (5,)
# 单批删除行数，避免长事务和大量 undo log 阻塞探测结果写入
PROBE_RETENTION_BATCH_SIZE = 5000


def _delete_before(time_column: InstrumentedAttribute[int], cutoff: int) -> int:
    """分批删除指定时间列早于保留边界的记录。

    参数:
        time_column: 待清理表的 Unix 秒时间列。
        cutoff: 保留边界，早于该时间戳的记录会被删除。
    返回:
        累计删除的记录数。
    """
    statement = (
        delete(time_column.class_)
        .where(time_column < cutoff)
        .with_dialect_options(mysql_limit=PROBE_RETENTION_BATCH_SIZE)
    )
    deleted_total = 0
    while True:
        with SessionLocal.begin() as session:
            deleted_count = session.execute(statement).rowcount
        deleted_total += deleted_count
        if deleted_count < PROBE_RETENTION_BATCH_SIZE:
            return deleted_total


def purge_expired_probe_records(current_time: int | None = None) -> dict[str, int]:
    """清理最近 60 个完整自然日之前的探测结果及告警事件。

    参数:
        current_time: 可选的当前 Unix 秒时间戳，默认取系统时间。
    返回:
        以表名为键、删除行数为值的清理统计。
    """
    cutoff = get_retention_cutoff(
        int(time()) if current_time is None else current_time,
        PROBE_RETENTION_DAYS,
    )
    time_columns = [model.time_id for model in PROBE_STATE_MODELS.values()]
    time_columns.append(AlertEvent.occurred_at)
    return {
        column.class_.__tablename__: _delete_before(column, cutoff)
        for column in time_columns
    }


def _seconds_until_next_run(current_time: datetime) -> float:
    """计算距离下一个北京时间清理时刻的秒数。

    参数:
        current_time: 带时区的当前时间。
    返回:
        距离下一个北京时间 5 点整的秒数。
    """
    local_time = current_time.astimezone(BEIJING_TIMEZONE)
    day_start = local_time.replace(hour=0, minute=0, second=0, microsecond=0)
    candidates = [
        day_start + timedelta(days=day_offset, hours=hour)
        for day_offset in (0, 1)
        for hour in PROBE_RETENTION_RUN_HOURS
    ]
    next_run = min(candidate for candidate in candidates if candidate > local_time)
    return (next_run - local_time).total_seconds()


async def run_probe_retention_scheduler() -> None:
    """常驻执行探测数据保留清理，每天北京时间 5 点执行一次。

    参数:
        无。
    返回:
        无返回值；协程持续运行直至被取消，单次清理失败仅记录日志。
    """
    while True:
        await asyncio.sleep(_seconds_until_next_run(datetime.now(BEIJING_TIMEZONE)))
        try:
            deleted_counts = await asyncio.to_thread(purge_expired_probe_records)
            logger.info("探测数据保留清理完成: %s", deleted_counts)
        except Exception:
            logger.exception("探测数据保留清理失败")
