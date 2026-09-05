import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import QRCode from 'qrcode'
import { ClawService, type OutBase, type OpenClawWeixinStatusOut } from '@/api'

const POLL_INTERVAL = 2000

export function useWeixinBinding(onBoundChange: (enabled: boolean) => Promise<void>) {
  const { t } = useI18n()
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
    if (result.code !== 200)
      throw new Error(result.message || t('setting.notify.openclawWeixinQrError'))
  }

  const loadStatus = async () => {
    statusLoading.value = true
    statusError.value = ''
    try {
      const result = await ClawService.getStatusApiSettingOpenclawWeixinStatusPost()
      checkResponse(result)
      status.value = result
    } catch (error) {
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
      const result = await ClawService.checkLoginApiSettingOpenclawWeixinLoginCheckPost({
        sessionId,
        ...(code ? { verifyCode: code } : {}),
      })
      if (id !== runId) return
      checkResponse(result)
      state.value = result.connected ? 'connected' : result.state || 'waiting'
      hint.value = result.message || t('setting.notify.openclawWeixinQrWaiting')
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
    hint.value = t('setting.notify.openclawWeixinQrLoading')
    try {
      const result = await ClawService.startLoginApiSettingOpenclawWeixinLoginStartPost()
      if (id !== runId) return
      checkResponse(result)
      if (!result.sessionId || !result.qrUrl)
        throw new Error(t('setting.notify.openclawWeixinQrInvalid'))
      const dataUrl = await QRCode.toDataURL(result.qrUrl, { width: 240, margin: 2 })
      if (id !== runId) return
      sessionId = result.sessionId
      qrDataUrl.value = dataUrl
      state.value = 'waiting'
      hint.value = t('setting.notify.openclawWeixinQrWaiting')
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
      checkResponse(await ClawService.unbindApiSettingOpenclawWeixinUnbindPost())
      await onBoundChange(false)
      await loadStatus()
      message.success(t('setting.notify.openclawWeixinUnbindSuccess'))
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
    verifyCode,
    loadStatus,
    close,
    start,
    submitCode,
    unbind,
  }
}
