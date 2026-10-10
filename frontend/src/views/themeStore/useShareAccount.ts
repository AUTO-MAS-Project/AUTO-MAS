import { computed, ref } from 'vue'

import { translate as t } from '@/i18n'
import { IDLE_SHARE_AUTH, useShareApi, type ShareAuthState } from '@/composables/useShareApi'
import { openExternalUrl } from '@/utils/openExternal'

/**
 * 主题商店的分享站登录：沿用通用脚本分享那套设备授权（浏览器里确认短码），
 * 桌面令牌只在后端内存里，离开页面只停轮询，不撤销正在等待的授权。
 */
export function useShareAccount(
  options: {
    onAuthorized?: (state: ShareAuthState) => void
    onError?: (message: string) => void
  } = {}
) {
  const logger = window.electronAPI.getLogger('主题商店')
  const { error, getShareAuthStatus, startShareAuth, pollShareAuth, cancelShareAuth } =
    useShareApi()

  const state = ref<ShareAuthState>({ ...IDLE_SHARE_AUTH })
  const starting = ref(false)
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let active = true

  const authorized = computed(() => state.value.status === 'authorized')
  const pending = computed(() => state.value.status === 'pending')
  const accountName = computed(() => state.value.displayName || state.value.username)

  const stopPolling = (): void => {
    if (pollTimer !== null) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  // 按分享站给的间隔轮询授权结果，拿到终态或页面离开就停
  const startPolling = (interval: number): void => {
    stopPolling()
    pollTimer = setTimeout(
      async () => {
        pollTimer = null
        if (!active) return
        const next = await pollShareAuth()
        if (!active) return
        if (!next) {
          startPolling(interval)
          return
        }
        state.value = next
        if (next.status === 'pending') {
          startPolling(next.interval || interval)
          return
        }
        if (next.status === 'authorized') options.onAuthorized?.(next)
      },
      Math.max(interval, 1) * 1000
    )
  }

  const openVerificationPage = (): void => {
    const uri = state.value.verificationUri
    // 地址由分享站下发，只放行普通网页链接
    if (/^https?:\/\//i.test(uri)) {
      openExternalUrl(uri)
      return
    }
    if (uri) logger.warn(`分享站返回了无法打开的授权地址: ${uri}`)
  }

  const refresh = async (): Promise<void> => {
    const next = await getShareAuthStatus()
    if (!active || !next) return
    state.value = next
    if (next.status === 'pending') startPolling(next.interval)
  }

  const login = async (): Promise<void> => {
    if (starting.value) return
    starting.value = true
    try {
      const next = await startShareAuth()
      if (!next) {
        options.onError?.(error.value ?? t('themeStore.account.startFailed'))
        return
      }
      state.value = next
      openVerificationPage()
      startPolling(next.interval)
    } finally {
      starting.value = false
    }
  }

  const cancel = async (): Promise<void> => {
    stopPolling()
    const next = await cancelShareAuth()
    state.value = next ?? { ...IDLE_SHARE_AUTH }
  }

  const dispose = (): void => {
    active = false
    stopPolling()
  }

  return {
    state,
    starting,
    authorized,
    pending,
    accountName,
    refresh,
    login,
    cancel,
    openVerificationPage,
    dispose,
  }
}

export type ShareAccount = ReturnType<typeof useShareAccount>
