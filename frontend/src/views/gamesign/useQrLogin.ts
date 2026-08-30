/**
 * 米游社扫码登录的会话状态机。
 *
 * 从 TabGameSign.vue 抽出来的部分：持有二维码会话（ticket/device）、轮询定时器、
 * AbortController 与展示状态；不碰账号列表、不碰弹窗以外的界面。
 *
 * 会话失效只认自己的 sessionId：每次 start() / cancel() 都让它自增，
 * 所有 await 之后都要重新比对，不一致就直接 return。
 * 原实现里 isCurrentQrSession 还隐含依赖「弹窗是否可见」，抽出来之后这条链会断，
 * 所以这里把弹窗可见性也一并收进来，并且只允许经由 cancel() 关闭——
 * 否则关弹窗时不会走到 abort/clearInterval，定时器会漏在后台。
 */
import { getCurrentInstance, onBeforeUnmount, ref } from 'vue'
import { message } from 'ant-design-vue'
import QRCode from 'qrcode'
import type { CancelablePromise, OutBase, QrCheckOut, QrCreateOut } from '@/api'
import { useGameSignApi } from './useGameSignApi'

export type QrLoginStatus =
  | 'idle'
  | 'loading'
  | 'waiting'
  | 'scanned'
  | 'exchanging'
  | 'done'
  | 'expired'
  | 'error'

type QrApiResponse = QrCreateOut & QrCheckOut & OutBase
type QrLogger = ReturnType<typeof window.electronAPI.getLogger>

export const QR_RESPONSE_INVALID_MESSAGE = '二维码状态响应无效，请刷新后重试'

const POLL_INTERVAL_MS = 2000
/** 成功后延迟关闭弹窗，让用户看到成功提示 */
const AUTO_CLOSE_DELAY_MS = 1200

/**
 * 判断后端返回的报错文案是否属于「二维码本身失效」。
 *
 * 这类错误要提示并允许重新生成，与本地主动取消是两回事：
 * 后者由 AbortError 静默吞掉，不能弹提示。
 */
export const isQrExpiredMessage = (messageText: string) =>
  /二维码|qr|expired|invalid|nonetype.*get|object has no attribute.*get/i.test(messageText)

const isQrAbortError = (error: unknown) => error instanceof Error && error.name === 'AbortError'

export interface QrLoginOptions {
  /** 当前正在编辑的账号 uid；取不到时只走完扫码流程，不落库 */
  getAccountId: () => string | undefined
  /**
   * 凭据已存进后端之后的本地同步（回填输入框、刷新列表、刷新配置）。
   * isStillCurrent 用来在每个 await 之后确认会话没被换掉。
   */
  onSaved: (
    accountId: string,
    cookiesStr: string,
    isStillCurrent: () => boolean
  ) => Promise<void> | void
  logger: QrLogger
}

export function useQrLogin({ getAccountId, onSaved, logger }: QrLoginOptions) {
  const { createMiyousheQr, checkMiyousheQr, saveMiyousheQr } = useGameSignApi()

  const visible = ref(false)
  const loading = ref(false)
  const status = ref<QrLoginStatus>('idle')
  const statusText = ref('')
  const qrCodeDataUrl = ref('')

  // 以下是会话内部状态，不对外暴露
  const ticket = ref('')
  const device = ref('')
  const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)
  const pollInFlight = ref(false)
  let sessionId = 0
  let abortController: AbortController | null = null
  let closeTimer: ReturnType<typeof setTimeout> | null = null

  const stopPoll = () => {
    if (pollTimer.value) {
      clearInterval(pollTimer.value)
      pollTimer.value = null
    }
  }

  const clearCloseTimer = () => {
    if (closeTimer) {
      clearTimeout(closeTimer)
      closeTimer = null
    }
  }

  /** 只比对 sessionId：弹窗可见性由 cancel() 统一维护，不再参与判定 */
  const isCurrentSession = (id: number) => id === sessionId

  /** 作废当前会话并返回新的 sessionId；幂等，重复调用只是继续自增 */
  const invalidateSession = () => {
    sessionId += 1
    stopPoll()
    clearCloseTimer()
    abortController?.abort()
    abortController = null
    pollInFlight.value = false
    return sessionId
  }

  /**
   * 把 openapi 生成的 CancelablePromise 接到 AbortSignal 上。
   * 取消导致的 reject 一律换成 name='AbortError'，好让调用方静默丢弃。
   */
  const abortableRequest = async <T>(
    request: CancelablePromise<T>,
    signal?: AbortSignal
  ): Promise<T> => {
    let aborted = signal?.aborted ?? false
    const handleAbort = () => {
      aborted = true
      request.cancel()
    }
    signal?.addEventListener('abort', handleAbort, { once: true })
    if (aborted) request.cancel()

    try {
      return await request
    } catch (error) {
      if (aborted) {
        const abortError = new Error('Request aborted')
        abortError.name = 'AbortError'
        throw abortError
      }
      throw error
    } finally {
      signal?.removeEventListener('abort', handleAbort)
    }
  }

  const qrFetch = async (
    path: '/create' | '/check' | '/save',
    body?: Record<string, string>,
    signal?: AbortSignal
  ): Promise<QrApiResponse> => {
    let response: QrApiResponse
    if (path === '/create') {
      response = await abortableRequest(createMiyousheQr(), signal)
    } else if (path === '/check') {
      response = await abortableRequest(
        checkMiyousheQr(body?.ticket || '', body?.device || ''),
        signal
      )
    } else {
      response = await abortableRequest(
        saveMiyousheQr(body?.account_uid || '', body?.cookie || ''),
        signal
      )
    }
    if (!response || typeof response !== 'object' || Array.isArray(response)) {
      throw new Error(QR_RESPONSE_INVALID_MESSAGE)
    }
    // 二维码 URL、ticket、设备标识和 Cookie 都是登录凭据，禁止写入前端日志。
    const logData = {
      ...response,
      ticket: undefined,
      qr_url: undefined,
      device: undefined,
      cookies_str: undefined,
    }
    logger.debug(`[QR ${path}] ${JSON.stringify(logData)}`)
    // 不在此处抛出 API 错误，由调用方根据 data.status / data.code 处理
    return response
  }

  const markExpired = (messageText = '二维码已过期，请刷新后重新扫码') => {
    stopPoll()
    status.value = 'expired'
    statusText.value = messageText
    qrCodeDataUrl.value = ''
  }

  /**
   * 关闭弹窗并作废会话。幂等——重复调用只是继续推进 sessionId。
   * 这是唯一允许把 visible 置回 false 的入口，绕过它会漏掉定时器清理。
   */
  const cancel = () => {
    invalidateSession()
    visible.value = false
    loading.value = false
    status.value = 'idle'
    qrCodeDataUrl.value = ''
    statusText.value = ''
    ticket.value = ''
    device.value = ''
  }

  const handleConfirmed = async (cookiesStr: string, id: number, signal: AbortSignal) => {
    if (!isCurrentSession(id)) return
    if (!cookiesStr) {
      status.value = 'error'
      statusText.value = '扫码确认成功但未获取到有效认证 Cookie，请重新生成二维码'
      return
    }

    // Passport 模式：cookies 直接从响应头获取，无需 exchange
    const accountId = getAccountId()
    if (accountId) {
      status.value = 'exchanging'
      statusText.value = '正在保存登录凭据...'
      try {
        const saveResponse = await qrFetch(
          '/save',
          { account_uid: accountId, cookie: cookiesStr },
          signal
        )
        if (!isCurrentSession(id)) return
        if (saveResponse.code !== 200 || saveResponse.status === 'error') {
          throw new Error(saveResponse.message || '保存 Token 失败')
        }
        await onSaved(accountId, cookiesStr, () => isCurrentSession(id))
        if (!isCurrentSession(id)) return
      } catch (error) {
        if (!isCurrentSession(id) || isQrAbortError(error)) return
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`扫码保存 Token 失败: ${errorMsg}`)
        message.error('扫码成功，但保存 Token 失败')
        status.value = 'error'
        statusText.value = '扫码成功，但保存 Token 失败'
        return
      }
    }
    status.value = 'done'
    statusText.value = '登录成功！Token 已自动填入'
    message.success('米游社扫码登录成功')
    clearCloseTimer()
    closeTimer = setTimeout(() => {
      closeTimer = null
      if (isCurrentSession(id)) cancel()
    }, AUTO_CLOSE_DELAY_MS)
  }

  /** 停轮询并转入错误态（与「二维码失效」区分：这条不提示重新生成） */
  const failPoll = (text: string) => {
    stopPoll()
    status.value = 'error'
    statusText.value = text
  }

  /** /check 返回体 -> 状态机推进；status === 'Init' 时不动 UI，继续轮询 */
  const applyCheckResult = async (data: QrApiResponse, id: number, signal: AbortSignal) => {
    const responseMessage = typeof data.message === 'string' ? data.message : ''

    // 后端错误响应（code=500 或 status=error）
    if (data.code === 500 || data.status === 'error') {
      if (isQrExpiredMessage(responseMessage)) markExpired(responseMessage)
      else failPoll(responseMessage || '查询状态失败')
      return
    }

    if (data.status === 'Scanned') {
      status.value = 'scanned'
      statusText.value = '已扫码，等待确认...'
    } else if (data.status === 'Confirmed') {
      stopPoll()
      await handleConfirmed(data.cookies_str || '', id, signal)
    } else if (data.status === 'Canceled') {
      failPoll(responseMessage || '登录已取消')
    } else if (data.status === 'Expired') {
      markExpired(responseMessage || '二维码已过期，请刷新后重新扫码')
    } else if (data.status === 'Error') {
      if (isQrExpiredMessage(responseMessage)) markExpired(responseMessage)
      else failPoll(responseMessage || '查询状态失败')
    }
  }

  const poll = async (id: number) => {
    if (!isCurrentSession(id) || pollInFlight.value || !ticket.value || !device.value) return
    const currentTicket = ticket.value
    const currentDevice = device.value
    const signal = abortController?.signal
    if (!signal) return

    pollInFlight.value = true
    try {
      const data = await qrFetch('/check', { ticket: currentTicket, device: currentDevice }, signal)
      if (!isCurrentSession(id)) return
      await applyCheckResult(data, id, signal)
    } catch (e) {
      if (!isCurrentSession(id) || isQrAbortError(e)) return
      const errorMessage = e instanceof Error ? e.message : String(e)
      if (isQrExpiredMessage(errorMessage) || errorMessage === QR_RESPONSE_INVALID_MESSAGE) {
        markExpired('二维码已失效或服务端返回无效状态，请刷新后重试')
      } else {
        // 短暂网络错误不停止轮询，但记录日志便于调试。
        logger.warn(`[QR poll] 轮询异常: ${errorMessage}`)
      }
    } finally {
      if (isCurrentSession(id)) pollInFlight.value = false
    }
  }

  /** 生成二维码并开始轮询。重复调用即「重新生成」，旧会话自动作废。 */
  const start = async () => {
    const id = invalidateSession()
    abortController = new AbortController()
    const { signal } = abortController
    loading.value = true
    status.value = 'loading'
    statusText.value = '正在生成二维码...'
    qrCodeDataUrl.value = ''
    ticket.value = ''
    device.value = ''
    visible.value = true

    try {
      const data = await qrFetch('/create', undefined, signal)
      if (!isCurrentSession(id)) return
      if (data.code === 500 || data.status === 'error') {
        status.value = 'error'
        statusText.value = data.message || '创建二维码失败'
        return
      }
      if (!data.qr_url || !data.ticket || !data.device) {
        throw new Error('创建二维码失败：服务端响应缺少登录信息')
      }
      // 先算好再判会话：原实现直接赋值给 qrCodeDataUrl，
      // 会话已被换掉时会把旧二维码写进新会话的界面。
      const dataUrl = await QRCode.toDataURL(data.qr_url, {
        width: 240,
        margin: 2,
        errorCorrectionLevel: 'M',
      })
      if (!isCurrentSession(id)) return
      qrCodeDataUrl.value = dataUrl
      ticket.value = data.ticket
      device.value = data.device
      status.value = 'waiting'
      statusText.value = '请使用米游社 APP 扫描二维码'
      pollTimer.value = setInterval(() => {
        void poll(id)
      }, POLL_INTERVAL_MS)
    } catch (e) {
      if (!isCurrentSession(id) || isQrAbortError(e)) return
      status.value = 'error'
      statusText.value = e instanceof Error ? e.message : String(e)
    } finally {
      if (isCurrentSession(id)) loading.value = false
    }
  }

  // 组件外调用（单测）时没有实例可挂，直接跳过——否则 Vue 会告警
  if (getCurrentInstance()) {
    onBeforeUnmount(() => {
      invalidateSession()
    })
  }

  return { visible, loading, status, statusText, qrCodeDataUrl, start, cancel }
}
