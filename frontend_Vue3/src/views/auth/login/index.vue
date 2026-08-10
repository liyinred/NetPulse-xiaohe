<!-- 微信扫码登录页面 -->
<template>
  <div class="flex w-full h-screen">
    <LoginLeftView />

    <div class="relative flex-1">
      <AuthTopBar />

      <div class="auth-right-wrap">
        <main class="form scan-login" aria-live="polite">
          <header class="scan-heading">
            <p class="scan-eyebrow">WECHAT / NETPULSE</p>
            <h3 class="title">{{ $t('login.title') }}</h3>
            <p class="sub-title">{{ $t('login.subTitle') }}</p>
          </header>

          <section class="qr-section" :aria-label="$t('login.scan.instruction')">
            <div class="qr-frame" :class="{ 'is-unavailable': isUnavailable }">
              <span class="corner corner-top-left"></span>
              <span class="corner corner-top-right"></span>
              <span class="corner corner-bottom-left"></span>
              <span class="corner corner-bottom-right"></span>

              <img
                v-if="qrCode"
                class="qr-image"
                :src="qrCode.imageUrl"
                :alt="$t('login.scan.qrAlt')"
              />
              <div v-else class="qr-placeholder">
                <ArtSvgIcon icon="ri:loader-4-line" class="loading-icon" />
              </div>

              <div v-if="isUnavailable" class="qr-overlay">
                <ElTooltip :content="$t('login.scan.refresh')" placement="top">
                  <button
                    class="refresh-button"
                    type="button"
                    :aria-label="$t('login.scan.refresh')"
                    @click="createLoginQRCode"
                  >
                    <ArtSvgIcon icon="ri:refresh-line" />
                  </button>
                </ElTooltip>
                <span>{{ statusText }}</span>
              </div>
            </div>

            <div class="scan-status">
              <span class="status-indicator" :class="`is-${loginStatus}`"></span>
              <span>{{ statusText }}</span>
            </div>
            <p v-if="qrCode && !isUnavailable" class="expiry-text">
              {{ $t('login.scan.expiresIn', { time: formattedRemainingTime }) }}
            </p>
          </section>

          <footer class="scan-instruction">
            <ArtSvgIcon icon="ri:wechat-line" />
            <span>{{ $t('login.scan.instruction') }}</span>
          </footer>
        </main>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import AppConfig from '@/config'
  import { fetchCreateWechatQRCode, fetchWechatLoginStatus } from '@/api/auth'
  import { useUserStore } from '@/store/modules/user'
  import { ElNotification } from 'element-plus'
  import { useI18n } from 'vue-i18n'

  defineOptions({ name: 'Login' })

  type LoginViewStatus = 'loading' | 'pending' | 'authenticated' | 'expired' | 'error'

  const POLLING_INTERVAL_MS = 2000
  const COUNTDOWN_INTERVAL_MS = 1000

  const { t } = useI18n()
  const userStore = useUserStore()
  const router = useRouter()
  const route = useRoute()
  const systemName = AppConfig.systemInfo.name

  const qrCode = ref<Api.Auth.WechatQRCode | null>(null)
  const loginStatus = ref<LoginViewStatus>('loading')
  const remainingSeconds = ref(0)
  const expiresAt = ref(0)
  const isPolling = ref(false)
  let pollingTimer: ReturnType<typeof setInterval> | undefined
  let countdownTimer: ReturnType<typeof setInterval> | undefined

  /** 标记二维码当前是否需要用户主动刷新。 */
  const isUnavailable = computed(() => ['expired', 'error'].includes(loginStatus.value))

  /** 将二维码剩余有效期格式化为分秒文本。 */
  const formattedRemainingTime = computed(() => {
    const minutes = Math.floor(remainingSeconds.value / 60)
    const seconds = remainingSeconds.value % 60
    return `${minutes}:${String(seconds).padStart(2, '0')}`
  })

  /** 根据当前认证状态生成界面提示。 */
  const statusText = computed(() => t(`login.scan.status.${loginStatus.value}`))

  /** 清理二维码轮询与倒计时定时器。 */
  const clearTimers = (): void => {
    if (pollingTimer) clearInterval(pollingTimer)
    if (countdownTimer) clearInterval(countdownTimer)
    pollingTimer = undefined
    countdownTimer = undefined
  }

  /** 按二维码服务端有效期刷新剩余秒数。 */
  const updateCountdown = (): void => {
    remainingSeconds.value = Math.max(0, Math.ceil((expiresAt.value - Date.now()) / 1000))
    if (remainingSeconds.value === 0 && loginStatus.value === 'pending') {
      loginStatus.value = 'expired'
      clearTimers()
    }
  }

  /** 展示登录成功通知。 */
  const showLoginSuccessNotice = (): void => {
    ElNotification({
      title: t('login.success.title'),
      type: 'success',
      duration: 2500,
      zIndex: 10000,
      message: `${t('login.success.message')}, ${systemName}!`
    })
  }

  /** 保存 JWT 并跳转至登录前页面。 */
  const completeLogin = async (token: string): Promise<void> => {
    clearTimers()
    loginStatus.value = 'authenticated'
    userStore.setToken(token)
    userStore.setLoginStatus(true)
    showLoginSuccessNotice()
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.push(redirect)
  }

  /** 查询当前二维码是否已由微信用户扫码。 */
  const pollLoginStatus = async (): Promise<void> => {
    if (!qrCode.value || isPolling.value || loginStatus.value !== 'pending') return
    isPolling.value = true
    try {
      const result = await fetchWechatLoginStatus(qrCode.value.sceneStr)
      if (result.status === 'expired') {
        loginStatus.value = 'expired'
        clearTimers()
      } else if (result.status === 'authenticated' && result.token) {
        await completeLogin(result.token)
      }
    } catch {
      loginStatus.value = 'error'
      clearTimers()
    } finally {
      isPolling.value = false
    }
  }

  /** 启动二维码状态轮询和有效期倒计时。 */
  const startTimers = (): void => {
    updateCountdown()
    pollingTimer = setInterval(pollLoginStatus, POLLING_INTERVAL_MS)
    countdownTimer = setInterval(updateCountdown, COUNTDOWN_INTERVAL_MS)
  }

  /** 请求新的微信服务号登录二维码。 */
  const createLoginQRCode = async (): Promise<void> => {
    clearTimers()
    qrCode.value = null
    loginStatus.value = 'loading'
    try {
      const result = await fetchCreateWechatQRCode()
      qrCode.value = result
      expiresAt.value = Date.now() + result.expireSeconds * 1000
      loginStatus.value = 'pending'
      startTimers()
    } catch {
      loginStatus.value = 'error'
    }
  }

  onMounted(createLoginQRCode)
  onUnmounted(clearTimers)
</script>

<style scoped>
  @import './style.css';
</style>
