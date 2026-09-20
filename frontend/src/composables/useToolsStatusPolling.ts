import { onUnmounted } from 'vue'
import { useEventListener } from '@vueuse/core'
import { Service, type ToolsConfig } from '@/api'

/** 工具处于启用/运行态时的轮询间隔 */
const ACTIVE_INTERVAL_MS = 5000
/** 工具未启用时的轮询间隔 */
const IDLE_INTERVAL_MS = 30000

interface ToolsStatusPollingOptions {
  /** 拿到最新配置后只回写状态类字段，不碰编辑态 */
  applyStatus: (data: ToolsConfig) => void
  /** 工具处于启用/运行态时用短间隔，否则长间隔 */
  isActive: () => boolean
  /** 当前是否需要刷新（例如页签不在签到页时跳过），省略视为一直需要 */
  enabled?: () => boolean
  /** 后端返回体无效时的提示文案 */
  invalidMessage: () => string
  logger: ReturnType<typeof window.electronAPI.getLogger>
}

/**
 * 工具页状态轮询：状态由 POST /api/tools/get 整份带回，页面只取其中的 Status 字段。
 *
 * 窗口隐藏时停掉定时器，回到前台（focus / visibilitychange）先补一次再按当前状态续排。
 * 用 setTimeout 链而不是 setInterval，这样每一轮都能按最新状态重新选间隔。
 */
export function useToolsStatusPolling(options: ToolsStatusPollingOptions) {
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let statusRequest: Promise<void> | null = null
  let statusPollFailed = false
  // 卸载守卫：组件卸载后阻止异步回调写入响应式状态
  let disposed = false

  const isEnabled = () => options.enabled?.() !== false

  // 仅更新状态（不影响编辑状态，不触发 loading）
  const updateStatus = () => {
    if (statusRequest) return statusRequest

    const request = (async () => {
      try {
        // 直接调用 Service 而非 getTools()，避免 loading 状态切换导致组件重渲染闪烁
        const response = await Service.getToolsApiToolsGetPost()
        if (disposed) return
        if (response.code !== 200 || !response.data) {
          throw new Error(response.message || options.invalidMessage())
        }
        statusPollFailed = false
        options.applyStatus(response.data)
      } catch (error) {
        if (!statusPollFailed) {
          const errorMsg = error instanceof Error ? error.message : String(error)
          options.logger.warn(`更新工具状态失败，将继续重试: ${errorMsg}`)
          statusPollFailed = true
        }
      }
    })()
    statusRequest = request
    void request.then(
      () => {
        if (statusRequest === request) statusRequest = null
      },
      () => {
        if (statusRequest === request) statusRequest = null
      }
    )
    return request
  }

  const clearTimer = () => {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  const scheduleNext = () => {
    clearTimer()
    if (disposed || document.hidden) return
    const delay = options.isActive() ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS
    pollTimer = setTimeout(async () => {
      if (isEnabled()) await updateStatus()
      scheduleNext()
    }, delay)
  }

  const startStatusPolling = () => scheduleNext()

  const stopStatusPolling = () => clearTimer()

  useEventListener(window, 'focus', () => {
    if (isEnabled()) void updateStatus()
  })
  // 隐藏时停掉定时器；回到前台先补一次，再按当前状态续排
  useEventListener(document, 'visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      if (isEnabled()) void updateStatus()
      scheduleNext()
    } else {
      clearTimer()
    }
  })

  onUnmounted(() => {
    disposed = true
    clearTimer()
  })

  return { updateStatus, startStatusPolling, stopStatusPolling }
}
