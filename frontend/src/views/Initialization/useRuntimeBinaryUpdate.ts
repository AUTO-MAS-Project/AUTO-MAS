import { computed, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { RuntimeBinaryUpdateCheck } from '@/types/electron'

export function useRuntimeBinaryUpdate(onUpdated: () => void) {
  const { t } = useI18n()
  const updating = ref(false)
  const updateMessage = ref('')
  const updateProgress = ref<number>()
  const updateCheck = ref<RuntimeBinaryUpdateCheck>()
  const canUpdateRuntime = computed(() => updateCheck.value?.status === 'available')
  const updateHint = computed(() => {
    const check = updateCheck.value
    if (!check || check.status === 'skipped') return ''
    const current = check.currentVersion || t('init.failure.runtimeVersionUnknown')
    if (check.status === 'available') {
      return t('init.failure.runtimeUpdateAvailable', { current, latest: check.target?.version })
    }
    return t('init.failure.runtimeVersion', { version: current })
  })
  let disposed = false

  async function checkForUpdate() {
    const api = window.electronAPI
    try {
      const result = await api.checkRuntimeBinaryUpdate()
      if (!disposed) updateCheck.value = result
    } catch (error) {
      api.getLogger('Runtime 更新').warn(`检查 Runtime 更新失败: ${String(error)}`)
    }
  }

  async function updateRuntime() {
    if (updating.value || !canUpdateRuntime.value) return
    updating.value = true
    updateMessage.value = t('init.failure.runtimeUpdating')
    updateProgress.value = undefined
    const api = window.electronAPI
    let restart = false
    try {
      api.onRuntimeBinaryProgress(progress => {
        updateMessage.value = progress.message
        updateProgress.value =
          progress.progress > 0 ? Math.min(100, Math.round(progress.progress)) : undefined
      })
      const result = await api.updateRuntimeBinary()
      switch (result.status) {
        case 'upgraded':
          updateMessage.value = t('init.failure.runtimeUpdated', {
            version: result.target?.version ?? '',
          })
          restart = true
          updateCheck.value = { status: 'current', currentVersion: result.target?.version }
          break
        case 'current':
          updateMessage.value = t('init.failure.runtimeCurrent', {
            version: result.target?.version ?? '',
          })
          updateCheck.value = { status: 'current', currentVersion: result.target?.version }
          break
        case 'skipped':
        case 'cancelled':
          updateMessage.value = t('init.failure.runtimeUpdateSkipped')
          break
        case 'failed':
          throw new Error(result.error || t('init.msg.execFailed'))
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error)
      api.getLogger('Runtime 更新').error(`更新 Runtime 失败: ${reason}`)
      updateMessage.value = t('init.failure.runtimeUpdateFailed', { error: reason })
      message.error(updateMessage.value)
    } finally {
      api.removeRuntimeBinaryProgressListener()
      updating.value = false
    }
    if (restart && !disposed) onUpdated()
  }

  onUnmounted(() => {
    disposed = true
    if (updating.value) window.electronAPI.removeRuntimeBinaryProgressListener()
  })

  return {
    updating,
    updateMessage,
    updateProgress,
    updateHint,
    canUpdateRuntime,
    checkForUpdate,
    updateRuntime,
  }
}
