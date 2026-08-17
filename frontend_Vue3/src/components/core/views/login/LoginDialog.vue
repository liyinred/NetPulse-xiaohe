<!-- 全局微信扫码登录弹窗 -->
<template>
  <ElDialog
    class="wechat-login-dialog"
    :model-value="!userStore.isLogin"
    :show-close="false"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :append-to-body="true"
    :aria-label="$t('login.title')"
  >
    <main class="login-dialog-content" aria-live="polite">
      <header class="login-dialog-header">
        <div class="login-dialog-brand" aria-hidden="true">
          <img src="@imgs/common/logo.webp" alt="" />
          <span>NetPulse</span>
        </div>
      </header>

      <section class="qr-section" :aria-label="$t('login.scan.instruction')">
        <div class="qr-frame" :class="{ 'is-unavailable': isUnavailable }">
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

        <p class="scan-instruction">
          <span>{{ $t('login.scan.prefix') }}</span>
          <ArtSvgIcon icon="ri:wechat-fill" />
          <strong>{{ $t('login.scan.instruction') }}</strong>
        </p>
        <div class="scan-status">
          <span class="status-indicator" :class="`is-${loginStatus}`"></span>
          <span>{{ statusText }}</span>
          <span v-if="qrCode && !isUnavailable" class="expiry-text">
            · {{ formattedRemainingTime }}
          </span>
        </div>
      </section>
    </main>
  </ElDialog>
</template>

<script setup lang="ts">
  import AppConfig from '@/config'
  import { fetchCreateWechatQRCode, fetchWechatLoginStatus } from '@/api/auth'
  import { useUserStore } from '@/store/modules/user'
  import { ElNotification } from 'element-plus'
  import { useI18n } from 'vue-i18n'

  defineOptions({ name: 'LoginDialog' })

  type LoginDialogStatus = 'loading' | 'pending' | 'authenticated' | 'expired' | 'error'

  const POLLING_INTERVAL_MS = 2000
  const COUNTDOWN_INTERVAL_MS = 1000

  const { t } = useI18n()
  const userStore = useUserStore()
  const router = useRouter()
  const systemName = AppConfig.systemInfo.name

  const qrCode = ref<Api.Auth.WechatQRCode | null>(null)
  const loginStatus = ref<LoginDialogStatus>('loading')
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

  /**
   * 保存 JWT 并恢复登录前访问地址。
   * @param token 服务端签发的 JWT access token。
   * @returns 登录状态和页面导航完成后的 Promise。
   */
  const completeLogin = async (token: string): Promise<void> => {
    clearTimers()
    loginStatus.value = 'authenticated'
    userStore.setToken(token)
    userStore.setLoginStatus(true)
    showLoginSuccessNotice()
    const redirectPath = userStore.loginRedirectPath
    userStore.setLoginRedirectPath('/')
    await router.replace(redirectPath)
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

  /**
   * 根据用户登录状态启动或停止二维码轮询。
   * @param isLogin 当前用户是否已登录。
   * @returns 无返回值。
   */
  const handleLoginStateChange = (isLogin: boolean): void => {
    if (isLogin) {
      clearTimers()
      return
    }
    createLoginQRCode()
  }

  watch(() => userStore.isLogin, handleLoginStateChange, { immediate: true })

  onUnmounted(clearTimers)
</script>

<style scoped>
  @reference '@styles/core/tailwind.css';

  :global(.wechat-login-dialog) {
    @apply w-11/12 max-w-md;

    background-color: var(--default-box-color);
    box-shadow: var(--el-box-shadow-dark);
  }

  :global(.wechat-login-dialog .el-dialog__header) {
    display: none;
  }

  :global(.wechat-login-dialog .el-dialog__body) {
    @apply !p-0;
  }

  .login-dialog-content {
    @apply flex flex-col items-center px-8 py-10 max-sm:px-6 max-sm:py-8;
  }

  .login-dialog-header {
    @apply flex flex-col items-center text-center;
  }

  .login-dialog-brand {
    @apply flex items-center gap-2 text-xl font-bold text-g-900;
  }

  .login-dialog-brand img {
    @apply w-10 h-10 object-contain;
  }

  .qr-section {
    @apply flex flex-col items-center mt-8;
  }

  .qr-frame {
    @apply relative w-64 max-w-full aspect-square p-4 border rounded-custom-sm;

    background-color: var(--default-box-color);
    border-color: var(--art-gray-200);
    box-shadow: var(--el-box-shadow-light);
  }

  .qr-image,
  .qr-placeholder {
    @apply block w-full h-full;
  }

  .qr-image {
    @apply object-contain;
  }

  .qr-placeholder {
    @apply grid place-items-center text-g-500 rounded-custom-xs;

    background-color: var(--art-gray-100);
  }

  .loading-icon {
    @apply text-3xl animate-spin;
  }

  .qr-overlay {
    @apply absolute inset-4 flex flex-col gap-3 items-center justify-center text-sm text-g-800;

    background-color: var(--default-box-color);
  }

  .refresh-button {
    @apply grid place-items-center w-11 aspect-square text-xl border-0 rounded-full cursor-pointer;

    color: var(--default-box-color);
    background-color: var(--main-color);
  }

  .refresh-button:focus-visible {
    @apply outline-2 outline-offset-2;

    outline-color: var(--main-color);
  }

  .scan-instruction {
    @apply flex flex-wrap gap-2 items-center justify-center mt-7 text-base text-g-700;
  }

  .scan-instruction .art-svg-icon {
    @apply text-xl;

    color: var(--el-color-success);
  }

  .scan-status {
    @apply flex items-center mt-3 text-xs text-g-500;
  }

  .status-indicator {
    @apply w-2 mr-2 aspect-square rounded-full bg-g-400;
  }

  .status-indicator.is-pending,
  .status-indicator.is-authenticated {
    background-color: var(--el-color-success);
  }

  .expiry-text {
    font-family: var(--app-font-family);
  }

  @media (prefers-reduced-motion: reduce) {
    .loading-icon {
      animation: none;
    }
  }
</style>
