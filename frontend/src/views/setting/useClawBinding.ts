import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import QRCode from 'qrcode'
import { beginAnalyticsOperation } from '@/utils/analytics'
import type { AnalyticsEventProps } from '@/types/analytics'
import {
  QqService,
  OpenClawQQTargetIn,
  type OutBase,
  type OpenClawQQStatusOut,
  type OpenClawQQGroupsOut,
} from '@/api'

const POLL_INTERVAL = 2000

const CHANNELS = {
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
  const groups = ref<OpenClawQQGroupsOut | null>(null)
  const groupsLoading = ref(false)
  const targetSaving = ref(false)
  const groupsError = ref('')
  let groupsRunId = 0
  let sessionId = ''
  let runId = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let statusTimer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  let isBound = false
  let enableAfterBind = false
  let qqBindingObserved = false
  let bindingAttempt: ReturnType<
    typeof beginAnalyticsOperation<'notification_binding_finished'>
  > | null = null
  let bindingAction: 'bind' | 'rebind' = 'bind'
  const finishBinding = (
    outcome: AnalyticsEventProps['notification_binding_finished']['outcome']
  ) => {
    bindingAttempt?.finish({ channel_kind: 'openclaw_qq', action: bindingAction, outcome })
    bindingAttempt = null
  }

  const checkResponse = (result: OutBase) => {
    if (result.code !== 200) throw new Error(result.message || label('QrError'))
  }

  const groupError = (code?: string) => {
    if (code === 'binding_changed') return label('BindingChanged')
    if (code === 'not_bound') return label('Unbound')
    return label('TargetError')
  }

  const loadGroups = async () => {
    if (groupsLoading.value || targetSaving.value || unbinding.value) return
    const id = ++groupsRunId
    groupsLoading.value = true
    groupsError.value = ''
    try {
      const result = await QqService.getGroupsApiSettingOpenclawQqGroupsPost()
      if (disposed || id !== groupsRunId) return
      if (result.code !== 200) throw new Error(label('GroupsError'))
      groups.value = result
    } catch {
      if (disposed || id !== groupsRunId) return
      groups.value = null
      groupsError.value = label('GroupsError')
    } finally {
      if (id === groupsRunId) groupsLoading.value = false
    }
  }

  const selectTarget = async (value: string) => {
    if (!groups.value?.bindingId || targetSaving.value) return
    const targetType = Object.values(OpenClawQQTargetIn.targetType).find(type => type === value)
    if (!targetType) return
    const id = ++groupsRunId
    targetSaving.value = true
    groupsLoading.value = false
    groupsError.value = ''
    try {
      const result = await QqService.setTargetApiSettingOpenclawQqTargetPost({
        bindingId: groups.value.bindingId,
        targetType,
      })
      if (disposed || id !== groupsRunId) return
      if (result.code !== 200) {
        groupsError.value = groupError(result.errorCode)
        return
      }
      groups.value = result
      message.success(label('TargetSaved'))
    } catch {
      if (!disposed && id === groupsRunId) groupsError.value = label('TargetError')
    } finally {
      targetSaving.value = false
    }
  }

  const loadStatus = async () => {
    clearTimeout(statusTimer)
    statusLoading.value = true
    statusError.value = ''
    try {
      const result = await api.status()
      checkResponse(result)
      status.value = result
      isBound = !!result.connected
      if (!result.connected || result.state === 'connected') {
        qqBindingObserved = false
      }
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
      clearTimeout(statusTimer)
      if (
        !disposed &&
        (qqBindingObserved || (status.value?.connected && status.value.state !== 'connected'))
      ) {
        statusTimer = setTimeout(() => void loadStatus(), POLL_INTERVAL)
      }
    }
  }

  const closeAttempt = (outcome: 'cancelled' | 'replaced' | 'unmounted') => {
    finishBinding(outcome)
    runId++
    clearTimeout(timer)
    open.value = false
    loading.value = checking.value = false
    sessionId = qrDataUrl.value = ''
    state.value = 'idle'
    hint.value = ''
  }
  const close = () => closeAttempt('cancelled')

  const poll = async (id: number) => {
    if (id !== runId || checking.value) return
    checking.value = true
    try {
      const result = await api.check({ sessionId })
      if (id !== runId) return
      checkResponse(result)
      const wasConnecting = state.value === 'connecting'
      state.value = result.connected ? 'connected' : result.state || 'waiting'
      hint.value = result.message || label('QrWaiting')
      if (state.value === 'connected') {
        finishBinding('connected')
        // 首次绑定默认启用；重新绑定只替换凭据，保留用户原来的开关状态。
        if (enableAfterBind) await onBoundChange(true)
        isBound = true
        await loadStatus()
        await loadGroups()
      } else if (['waiting', 'scanned', 'connecting'].includes(state.value)) {
        if (state.value === 'connecting' && !wasConnecting) {
          qqBindingObserved = true
          void loadStatus()
          void loadGroups()
        }
        timer = setTimeout(() => void poll(id), POLL_INTERVAL)
      } else {
        finishBinding(state.value === 'expired' ? 'expired' : 'failure')
      }
    } catch (error) {
      if (id !== runId) return
      finishBinding('failure')
      state.value = 'error'
      hint.value = String(error)
    } finally {
      if (id === runId) checking.value = false
    }
  }

  const start = async () => {
    if (targetSaving.value) return
    groupsRunId++
    groupsLoading.value = false
    isBound ||= status.value?.connected === true
    enableAfterBind = !isBound
    closeAttempt('replaced')
    bindingAction = isBound ? 'rebind' : 'bind'
    bindingAttempt = beginAnalyticsOperation('notification_binding_finished')
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
      finishBinding('failure')
      state.value = 'error'
      hint.value = String(error)
    } finally {
      if (id === runId) loading.value = false
    }
  }

  const unbind = async () => {
    if (targetSaving.value) return
    const activeBinding = bindingAttempt
    const operation = beginAnalyticsOperation('notification_binding_finished')
    groupsRunId++
    groupsLoading.value = false
    unbinding.value = true
    try {
      checkResponse(await api.unbind())
      if (bindingAttempt === activeBinding) finishBinding('cancelled')
      operation.finish({ channel_kind: 'openclaw_qq', action: 'unbind', outcome: 'unbound' })
      isBound = false
      qqBindingObserved = false
      groups.value = null
      await onBoundChange(false)
      await loadStatus()
      message.success(label('UnbindSuccess'))
    } catch (error) {
      operation.finish({ channel_kind: 'openclaw_qq', action: 'unbind', outcome: 'failure' })
      message.error(String(error))
    } finally {
      unbinding.value = false
    }
  }

  onMounted(loadStatus)
  onBeforeUnmount(() => {
    disposed = true
    groupsRunId++
    clearTimeout(statusTimer)
    closeAttempt('unmounted')
  })

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
    groups,
    groupsLoading,
    groupsError,
    targetSaving,
    loadGroups,
    selectTarget,
    loadStatus,
    close,
    start,
    unbind,
  }
}
