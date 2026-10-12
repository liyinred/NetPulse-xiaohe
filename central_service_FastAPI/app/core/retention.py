"""按北京时间自然日计算数据保留边界。"""

from datetime import datetime, timedelta, timezone


BEIJING_TIMEZONE = timezone(timedelta(hours=8))


def get_retention_cutoff(current_time: int, retention_days: int) -> int:
    """计算最近若干个完整自然日的保留边界。

    参数:
        current_time: 当前 Unix 时间戳，单位为秒。
        retention_days: 当天之外需要保留的完整自然日数量。
    返回:
        北京时间当天零点向前 retention_days 天对应的 Unix 时间戳，早于该值的记录可清理。
    """
    current_day_start = datetime.fromtimestamp(
        current_time,
        tz=BEIJING_TIMEZONE,
    ).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((current_day_start - timedelta(days=retention_days)).timestamp())
