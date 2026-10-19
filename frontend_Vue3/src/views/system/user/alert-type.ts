import type { TagProps } from 'element-plus'

type AlertTagType = TagProps['type']

export const ALERT_TYPE_OPTIONS = [
  { label: '不接收', value: 0 },
  { label: '异网告警', value: 1 },
  { label: '跨省告警', value: 2 },
  { label: '全部告警', value: 3 }
] as const

export const ALERT_TYPE_CONFIG: Record<
  Api.SystemManage.UserAlertType,
  { text: string; type: AlertTagType }
> = {
  0: { text: '不接收', type: 'info' },
  1: { text: '异网告警', type: 'primary' },
  2: { text: '跨省告警', type: 'warning' },
  3: { text: '全部告警', type: 'success' }
}
