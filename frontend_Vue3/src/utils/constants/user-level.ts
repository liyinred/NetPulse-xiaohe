export const USER_LEVEL_CONFIG = {
  1: { text: '普通用户', type: 'info' as const },
  2: { text: '高级用户', type: 'warning' as const },
  9: { text: '管理员', type: 'danger' as const }
}

export const USER_LEVEL_OPTIONS = [
  { label: '普通用户', value: 1 },
  { label: '高级用户', value: 2 },
  { label: '管理员', value: 9 }
] as const

/**
 * 获取用户等级的展示配置。
 * @param userLevel 用户等级编码。
 * @returns 等级文案和 ElTag 类型。
 */
export function getUserLevelConfig(userLevel: number | undefined) {
  if (userLevel === undefined) return { text: '未知', type: 'info' as const }
  return (
    USER_LEVEL_CONFIG[userLevel as keyof typeof USER_LEVEL_CONFIG] ?? {
      text: '未知',
      type: 'info' as const
    }
  )
}
