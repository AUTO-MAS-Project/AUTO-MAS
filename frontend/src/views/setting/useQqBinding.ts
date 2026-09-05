import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import QRCode from 'qrcode'
import { QqService, type OpenClawQQStatusOut, type OutBase } from '@/api'

const POLL_INTERVAL = 2000

export function useQqBinding(onBoundChange: (enabled: boolean) => Promise<void>) {
  const { t } = useI18n()
  const status = ref<OpenClawQQStatusOut | null>(null)
  const statusLoading = ref(false)
  const statusError = ref('')
  const unbinding = ref(false)
  const open = ref(false)
  const loading = ref(false)
  const checking = ref(false)
  const qrDataUrl = ref('')
  const state = ref('idle')
  const hint = ref('')
  let sessionId = ''
  let runId = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  const checkResponse = (result: OutBase) => {
    if (result.code !== 200)
      throw new Error(result.message || t('setting.notify.openclawQqQrError'))
  }

  const loadStatus = async () => {
    statusLoading.value = true
    statusError.value = ''
    try {
      const result = await QqService.getStatusApiSettingOpenclawQqStatusPost()
      checkResponse(result)
      status.value = result
      // 后端发现凭据不完整时同时关闭旧的通知开关，避免继续向失效渠道投递。
      if (result.enabled && !result.connected) {
        try {
          await onBoundChange(false)
          status.value = { ...result, enabled: false }
        } catch (error) {
          statusError.value = String(error)
        }
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
    if (timer) clearTimeout(timer)
    timer = undefined
    open.value = false
    loading.value = checking.value = false
    sessionId = qrDataUrl.value = ''
    state.value = 'idle'
    hint.value = ''
  }

  const poll = async (id: number) => {
    if (id !== runId || checking.value) return
    checking.value = true
    try {
      const result = await QqService.checkLoginApiSettingOpenclawQqLoginCheckPost({
        sessionId,
      })
      if (id !== runId) return
      checkResponse(result)
      state.value = result.connected ? 'connected' : result.state || 'waiting'
      hint.value = result.message || t('setting.notify.openclawQqQrWaiting')
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
    hint.value = t('setting.notify.openclawQqQrLoading')
    try {
      const result = await QqService.startLoginApiSettingOpenclawQqLoginStartPost()
      if (id !== runId) return
      checkResponse(result)
      if (!result.sessionId || !result.qrUrl)
        throw new Error(t('setting.notify.openclawQqQrInvalid'))
      const dataUrl = await QRCode.toDataURL(result.qrUrl, { width: 240, margin: 2 })
      if (id !== runId) return
      sessionId = result.sessionId
      qrDataUrl.value = dataUrl
      state.value = 'waiting'
      hint.value = t('setting.notify.openclawQqQrWaiting')
      void poll(id)
    } catch (error) {
      if (id !== runId) return
      state.value = 'error'
      hint.value = String(error)
    } finally {
      if (id === runId) loading.value = false
    }
  }

  const unbind = async () => {
    unbinding.value = true
    try {
      checkResponse(await QqService.unbindApiSettingOpenclawQqUnbindPost())
      await onBoundChange(false)
      await loadStatus()
      message.success(t('setting.notify.openclawQqUnbindSuccess'))
    } catch (error) {
      message.error(String(error))
    } finally {
      unbinding.value = false
    }
  }

  onMounted(loadStatus)
  onBeforeUnmount(close)

  return {
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
    loadStatus,
    close,
    start,
    unbind,
  }
}
