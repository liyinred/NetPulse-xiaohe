<!-- 用户管理页表头 CDK 展示 -->
<template>
  <div class="flex flex-wrap items-center gap-2">
    <template v-if="cdk">
      <span class="text-sm text-g-600">高级用户CDK：</span>
      <span class="font-mono text-sm font-medium tracking-wider text-g-900">{{ displayCode }}</span>
      <ElTag :type="remainingSeconds <= WARNING_THRESHOLD_SECONDS ? 'warning' : 'success'">
        剩余 {{ formattedRemaining }}
      </ElTag>
      <ElButton size="small" :icon="CopyDocument" @click="handleCopy">复制</ElButton>
    </template>
    <template v-else>
      <span class="text-sm text-g-600">{{ loading ? 'CDK 获取中…' : 'CDK 获取失败' }}</span>
      <ElButton v-if="!loading" size="small" @click="loadCdk">重新获取</ElButton>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { CopyDocument } from '@element-plus/icons-vue'
  import { ElButton, ElMessage, ElTag } from 'element-plus'
  import { useClipboard, useDocumentVisibility, useIntervalFn } from '@vueuse/core'
  import { fetchGetCurrentCdk } from '@/api/system-manage'

  defineOptions({ name: 'CdkCode' })

  /** 剩余时间进入提醒色的阈值（秒） */
  const WARNING_THRESHOLD_SECONDS = 120
  /** 获取失败后自动重试的间隔（秒） */
  const RETRY_INTERVAL_SECONDS = 10

  const cdk = ref<Api.SystemManage.CdkInfo>()
  const remainingSeconds = ref(0)
  const loading = ref(false)
  /** 下次允许自动重试的时间戳，避免接口失败后每秒重复请求 */
  let nextRetryAt = 0

  const { copy, isSupported } = useClipboard()

  /** 按 4 位一组格式化当前 CDK */
  const displayCode = computed(() => {
    if (!cdk.value) return ''
    const groups = cdk.value.code.match(/.{1,4}/g) ?? []
    return `CDK-${groups.join('-')}`
  })

  /** 将剩余秒数格式化为 mm:ss */
  const formattedRemaining = computed(() => {
    const minutes = Math.floor(remainingSeconds.value / 60)
    const seconds = remainingSeconds.value % 60
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  })

  /**
   * 从后端读取当前 CDK，并按服务端时间差重置倒计时。
   * @returns 请求完成后的 Promise。
   */
  async function loadCdk(): Promise<void> {
    if (loading.value) return
    loading.value = true
    try {
      const data = await fetchGetCurrentCdk()
      cdk.value = data
      // 使用服务端返回的时间差，避免浏览器时钟偏差影响倒计时。
      remainingSeconds.value = Math.max(0, data.expireTime - data.serverTime)
      nextRetryAt = 0
    } catch {
      // HTTP 层已统一提示错误，保留上一次成功的码（如有），并按固定间隔自动重试。
      nextRetryAt = Date.now() + RETRY_INTERVAL_SECONDS * 1000
    } finally {
      loading.value = false
    }
  }

  /**
   * 每秒推进倒计时；归零或获取失败后按间隔重新向后端请求当前码。
   * @returns 无返回值。
   */
  function tick(): void {
    if (remainingSeconds.value > 0) {
      remainingSeconds.value -= 1
      if (remainingSeconds.value === 0) void loadCdk()
      return
    }
    if (Date.now() >= nextRetryAt) void loadCdk()
  }

  /**
   * 将带分组格式的 CDK 复制到剪贴板。
   * @returns 无返回值。
   */
  async function handleCopy(): Promise<void> {
    if (!displayCode.value) return
    if (!isSupported.value) {
      ElMessage.error('当前浏览器不支持复制')
      return
    }
    await copy(displayCode.value)
    ElMessage.success('CDK 已复制')
  }

  useIntervalFn(tick, 1000)

  // 浏览器会节流后台标签页的定时器，切回页面时需按服务端时间重新同步，
  // 避免继续展示已经过期的码和失真的倒计时。
  const documentVisibility = useDocumentVisibility()
  watch(documentVisibility, (visibility) => {
    if (visibility === 'visible') void loadCdk()
  })

  onMounted(() => {
    void loadCdk()
  })
</script>
