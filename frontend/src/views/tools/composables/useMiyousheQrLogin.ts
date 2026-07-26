/**
 * Lane 8：米游社扫码登录状态管理。
 *
 * 从 TabGameSign.vue 拆分出来，负责：
 * - 创建二维码
 * - 轮询扫码状态
 * - 扫码确认后保存 Token
 * - 组件卸载时清理轮询定时器
 *
 * 设计：composable 只负责状态与逻辑，UI 由 MiyousheQrModal.vue 渲染。
 */
import { onBeforeUnmount, ref } from 'vue'
import { message } from 'ant-design-vue'
import { OpenAPI } from '@/api'
import { authenticatedApiFetch } from '@/utils/httpSecurity'

export type QrStatus = 'idle' | 'loading' | 'waiting' | 'scanned' | 'exchanging' | 'done' | 'error'

export interface UseMiyousheQrLoginOptions {
  /** 日志器（来自 window.electronAPI.getLogger） */
  logger: {
    debug: (...args: any[]) => void
    info: (...args: any[]) => void
    warn: (...args: any[]) => void
    error: (...args: any[]) => void
  }
  /**
   * 扫码确认后回调，用于将 Token 写入编辑中的账号并保存。
   * 返回 true 表示保存成功，false 表示失败。
   */
  onConfirmed: (cookiesStr: string) => Promise<boolean>
  /** Token 保存成功后刷新外部数据（如 accounts / config） */
  onRefresh?: () => Promise<void>
}

export function useMiyousheQrLogin(options: UseMiyousheQrLoginOptions) {
  const { logger, onConfirmed, onRefresh } = options

  const modalVisible = ref(false)
  const loading = ref(false)
  const status = ref<QrStatus>('idle')
  const statusText = ref('')
  const qrUrl = ref('')
  const ticket = ref('')
  const device = ref('')
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let pollInFlight = false
  let activeRequest: AbortController | null = null
  let sessionGeneration = 0
  // 连续轮询失败计数，超过阈值后停止轮询并提示用户
  let pollFailCount = 0
  const POLL_FAIL_THRESHOLD = 3

  const qrFetch = async (path: string, body?: any, signal?: AbortSignal) => {
    const resp = await authenticatedApiFetch(`${OpenAPI.BASE}/api/tools/sign/miyoushe/qr${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal,
    })
    const text = await resp.text()
    if (!text) throw new Error('服务器无响应')
    const data = JSON.parse(text)
    // /check 成功响应包含 cookies_str，禁止把完整载荷写入 renderer 日志。
    logger.debug(`[QR ${path}] code=${String(data.code ?? '')} status=${String(data.status ?? '')}`)
    return data
  }

  const stopPoll = () => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    activeRequest?.abort()
    activeRequest = null
    pollInFlight = false
  }

  const close = () => {
    sessionGeneration += 1
    stopPoll()
    modalVisible.value = false
    status.value = 'idle'
    qrUrl.value = ''
    ticket.value = ''
    device.value = ''
  }

  const start = async () => {
    sessionGeneration += 1
    stopPoll()
    const activeSession = sessionGeneration
    loading.value = true
    status.value = 'loading'
    statusText.value = '正在生成二维码...'
    modalVisible.value = true

    try {
      activeRequest = new AbortController()
      const data = await qrFetch('/create', undefined, activeRequest.signal)
      if (activeSession !== sessionGeneration) return
      if (data.code !== 200 || data.status === 'error') {
        status.value = 'error'
        statusText.value = data.message || '创建二维码失败'
        return
      }
      pollFailCount = 0
      qrUrl.value = data.qr_url
      ticket.value = data.ticket
      device.value = data.device
      status.value = 'waiting'
      statusText.value = '请使用米游社 APP 扫描二维码'
      pollTimer = setInterval(() => void poll(activeSession), 2000)
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return
      if (activeSession !== sessionGeneration) return
      status.value = 'error'
      statusText.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (activeSession === sessionGeneration) {
        loading.value = false
        activeRequest = null
      }
    }
  }

  const poll = async (activeSession: number) => {
    if (activeSession !== sessionGeneration || pollInFlight) return
    pollInFlight = true
    activeRequest = new AbortController()
    try {
      const data = await qrFetch(
        '/check',
        { ticket: ticket.value, device: device.value },
        activeRequest.signal
      )
      if (activeSession !== sessionGeneration) return

      if (data.code !== 200 || data.status === 'error') {
        stopPoll()
        status.value = 'error'
        statusText.value = data.message || '查询状态失败'
        return
      }

      pollFailCount = 0

      if (data.status === 'Scanned') {
        status.value = 'scanned'
        statusText.value = '已扫码，等待确认...'
      } else if (data.status === 'Confirmed') {
        stopPoll()
        await handleConfirmed(data.cookies_str, activeSession)
      } else if (data.status === 'Canceled') {
        stopPoll()
        status.value = 'error'
        statusText.value = '登录已取消'
      } else if (data.status === 'Expired') {
        stopPoll()
        status.value = 'error'
        statusText.value = '二维码已过期，请重新生成'
      } else if (data.status === 'Error') {
        stopPoll()
        status.value = 'error'
        statusText.value = data.message || '查询状态失败'
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return
      if (activeSession !== sessionGeneration) return
      pollFailCount += 1
      logger.warn(`[QR poll] 轮询异常 (${pollFailCount}/${POLL_FAIL_THRESHOLD}): ${String(e)}`)
      if (pollFailCount >= POLL_FAIL_THRESHOLD) {
        stopPoll()
        status.value = 'error'
        statusText.value = '网络异常，请重试'
        message.error('扫码轮询连续失败，已停止，请重新生成二维码')
      }
    } finally {
      if (activeSession === sessionGeneration) {
        activeRequest = null
        pollInFlight = false
      }
    }
  }

  const handleConfirmed = async (cookiesStr: string, activeSession: number) => {
    if (activeSession !== sessionGeneration) return
    if (!cookiesStr) {
      status.value = 'error'
      statusText.value = '扫码确认成功但未获取到凭据'
      return
    }

    try {
      const ok = await onConfirmed(cookiesStr)
      if (activeSession !== sessionGeneration) return
      if (!ok) {
        status.value = 'error'
        statusText.value = '扫码成功，但保存 Token 失败'
        return
      }
      if (onRefresh) {
        await onRefresh()
        if (activeSession !== sessionGeneration) return
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`扫码保存 Token 失败: ${errorMsg}`)
      message.error('扫码成功，但保存 Token 失败')
      status.value = 'error'
      statusText.value = '扫码成功，但保存 Token 失败'
      return
    }
    status.value = 'done'
    statusText.value = '登录成功！Token 已自动填入'
    message.success('米游社扫码登录成功')
    setTimeout(() => close(), 1200)
  }

  onBeforeUnmount(() => {
    stopPoll()
  })

  return {
    modalVisible,
    loading,
    status,
    statusText,
    qrUrl,
    start,
    close,
  }
}
