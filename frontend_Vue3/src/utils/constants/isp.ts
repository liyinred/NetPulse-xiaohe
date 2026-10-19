/** 运营商编码与名称映射，与后端 ISP_NAMES 保持一致 */
export const ISP_NAMES: Record<number, string> = {
  1: '电信',
  2: '移动',
  3: '联通',
  4: '其他运营商'
}

/** 其他运营商编码 */
export const OTHER_ISP_CODE = 4

/** 运营商下拉选项 */
export const ISP_OPTIONS = Object.entries(ISP_NAMES).map(([value, label]) => ({
  label,
  value: Number(value)
}))

/** 三大运营商下拉选项，不含其他运营商 */
export const MAJOR_ISP_OPTIONS = ISP_OPTIONS.filter((option) => option.value !== OTHER_ISP_CODE)
