import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import QRCode from 'qrcode'
import { ClawService, QqService, type OutBase, type OpenClawWeixinStatusOut } from '@/api'

const POLL_INTERVAL = 2000

const CHANNELS = {
  weixin: {
    prefix: 'openclawWeixin',
    status: ClawService.getStatusApiSettingOpenclawWeixinStatusPost,
    start: ClawService.startLoginApiSettingOpenclawWeixinLoginStartPost,
    check: ClawService.checkLoginApiSettingOpenclawWeixinLoginCheckPost,
    unbind: ClawService.unbindApiSettingOpenclawWeixinUnbindPost,
  },
  qq: {
    prefix: 'openclawQq',
    status: QqService.getStatusApiSettingOpenclawQqStatusPost,
    start: QqService.startLoginApiSettingOpenclawQqLoginStartPost,
    check: QqService.checkLoginApiSettingOpenclawQqLoginCheckPost,
    unbind: QqService.unbindApiSettingOpenclawQqUnbindPost,
  },
}

export type ClawChannel = keyof typeof CHANNELS

export function useClawBinding(
  channel: ClawChannel,
  onBoundChange: (enabled: boolean) => Promise<void>
) {
  const api = CHANNELS[channel]
  const { t } = useI18n()
  const label = (key: string) => t(`setting.notify.${api.prefix}${key}`)
  const status = ref<OpenClawWeixinStatusOut | null>(null)
  const statusLoading = ref(false)
  const statusError = ref('')
  const unbinding = ref(false)
  const open = ref(false)
  const loading = ref(false)
  const checking = ref(false)
  const qrDataUrl = ref('')
  const state = ref('idle')
  const hint = ref('')
  const verifyCode = ref('')
  let sessionId = ''
  let runId = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  const checkResponse = (result: OutBase) => {
    if (result.code !== 200) throw new Error(result.message || label('QrError'))
  }

  const loadStatus = async () => {
    statusLoading.value = true
    statusError.value = ''
    try {
      const result = await api.status()
      checkResponse(result)
      status.value = result
      // 后端发现凭据不完整时同时关闭旧的通知开关，避免继续向失效渠道投递。
      if (result.enabled && !result.connected) {
        await onBoundChange(false)
        status.value = { ...result, enabled: false }
      }
    } catch (error) {
      // 查询失败时清空旧状态，避免新的错误仍沿用上一次的「已绑定」。
      status.value = null
      statusError.value = String(error)
    } finally {
      statusLoading.value = false
    }
  }

  const close = () => {
    runId++
    clearTimeout(timer)
    open.value = false
    loading.value = checking.value = false
    sessionId = qrDataUrl.value = verifyCode.value = ''
    state.value = 'idle'
    hint.value = ''
  }

  const poll = async (id: number, code?: string) => {
    if (id !== runId || checking.value) return
    checking.value = true
    try {
      const result = await api.check({
        sessionId,
        ...(code ? { verifyCode: code } : {}),
      })
      if (id !== runId) return
      checkResponse(result)
      state.value = result.connected ? 'connected' : result.state || 'waiting'
      hint.value = result.message || label('QrWaiting')
      if (state.value === 'connected') {
        await onBoundChange(true)
        await loadStatus()
      } else if (['waiting', 'scanned'].includes(state.value)) {
        timer = setTimeout(() => void poll(id), POLL_INTERVAL)
      }
    } catch (error) {
      if (id !== runId) return
      state.value = 'error'
      hint.value = String(error)
    } finally {
      if (id === runId) checking.value = false
    }
  }

  const start = async () => {
    close()
    const id = runId
    open.value = loading.value = true
    state.value = 'loading'
    hint.value = label('QrLoading')
    try {
      const result = await api.start()
      if (id !== runId) return
      checkResponse(result)
      if (!result.sessionId || !result.qrUrl) throw new Error(label('QrInvalid'))
      const dataUrl = await QRCode.toDataURL(result.qrUrl, { width: 240, margin: 2 })
      if (id !== runId) return
      sessionId = result.sessionId
      qrDataUrl.value = dataUrl
      state.value = 'waiting'
      hint.value = label('QrWaiting')
      void poll(id)
    } catch (error) {
      if (id !== runId) return
      state.value = 'error'
      hint.value = String(error)
    } finally {
      if (id === runId) loading.value = false
    }
  }

  const submitCode = () => {
    if (verifyCode.value.trim()) void poll(runId, verifyCode.value.trim())
  }

  const unbind = async () => {
    unbinding.value = true
    try {
      checkResponse(await api.unbind())
      await onBoundChange(false)
      await loadStatus()
      message.success(label('UnbindSuccess'))
    } catch (error) {
      message.error(String(error))
    } finally {
      unbinding.value = false
    }
  }

  onMounted(loadStatus)
  onBeforeUnmount(close)

  return {
    label,
    status,
    statusLoading,
    statusError,
    unbinding,
    open,
    loading,
    checking,
    qrDataUrl,
    state,
    hint,
    verifyCode,
    loadStatus,
    close,
    start,
    submitCode,
    unbind,
  }
}
