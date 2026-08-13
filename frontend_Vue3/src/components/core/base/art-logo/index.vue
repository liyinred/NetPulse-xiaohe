<!-- 系统logo -->
<template>
  <div class="flex-cc">
    <img :style="logoStyle" src="@imgs/common/logo.webp" alt="logo" class="w-full h-full" />
  </div>
</template>

<script setup lang="ts">
  defineOptions({ name: 'ArtLogo' })

  interface Props {
    /** logo 大小 */
    size?: number | string
  }

  const props = withDefaults(defineProps<Props>(), {
    size: 36
  })

  /**
   * 标准化 Logo 尺寸，数字及纯数字字符串使用 px，其他字符串保留 CSS 单位或变量。
   * @param size Logo 尺寸
   * @returns 可用于 CSS width 的尺寸值
   */
  const normalizeLogoSize = (size: number | string): string => {
    const normalizedSize = String(size).trim()
    return normalizedSize !== '' && Number.isFinite(Number(normalizedSize))
      ? `${normalizedSize}px`
      : normalizedSize
  }

  /**
   * 生成 Logo 尺寸样式。
   * @returns Logo 宽度样式
   */
  const logoStyle = computed(() => ({
    width: normalizeLogoSize(props.size)
  }))
</script>
