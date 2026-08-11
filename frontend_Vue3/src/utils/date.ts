/**
 * 将 Unix 秒时间戳格式化为北京时间。
 * @param timestamp Unix 秒时间戳。
 * @returns YYYY-MM-DD HH:MM:SS 格式的北京时间，空值返回短横线。
 */
export function formatBeijingTime(timestamp: number | null): string {
  if (timestamp === null) return '-'
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23'
  }).format(new Date(timestamp * 1000))
}

/**
 * 将 Unix 秒时间戳格式化为曲线横轴使用的北京时间。
 * @param timestamp Unix 秒时间戳。
 * @returns YY-MM-DD HH:MM 格式的北京时间。
 */
export function formatBeijingMinute(timestamp: number): string {
  return formatBeijingTime(timestamp).slice(2, 16)
}
