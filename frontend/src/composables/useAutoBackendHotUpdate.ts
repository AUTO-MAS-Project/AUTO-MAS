import { computed, h } from 'vue'
import { storeToRefs } from 'pinia'
import { Button, notification } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { reconnectNow, onConnected } from '@/services/websocket/connection'
import { getBackendVersion } from '@/composables/useVersionService'
import { useBackendHotUpdateStore } from '@/stores/backendHotUpdate'
import type { HotUpdateRecord, HotUpdateRepairMode, RuntimeUpdateOutcome } from '@/types/electron'

interface LifecycleHooks {
  begin: (reason: string) => void
  end: (reason: string) => void
  refreshState: () => Promise<void> | void
  isConnected?: () => boolean
}

let store: ReturnType<typeof useBackendHotUpdateStore> | undefined
let hooks: LifecycleHooks | undefined
let disposeListeners: (() => void) | undefined
let generation = 0
let mutation = 0
let connectionSeen = false
const connecting = new Set<string>()
const delivered = new Set<string>()
const notifying = new Set<string>()
const refreshedOperations = new Set<string>()
const logger = () => window.electronAPI.getLogger('后端热更新')
const warn = (error: unknown) => logger().warn(String(error))

export const isAutoBackendHotUpdateBlocking = (): boolean => store?.blocked === true

function openRecovery(): void {
  if (store) store.recoveryVisible = true
}

function resultFingerprint(record: HotUpdateRecord): string {
  return record.result === 'failed'
    ? `${record.targetCommit}:${record.phase}:${record.code ?? record.error}`
    : String(record.result)
}

function notifyResult(record: HotUpdateRecord): void {
  const result = record.result
  if (
    !result ||
    record.notified ||
    (result === 'success' && (!connectionSeen || hooks?.isConnected?.() === false))
  )
    return
  const fingerprint = resultFingerprint(record)
  if (result === 'failed' && record.notifiedFailure === fingerprint) return
  const key = `${record.operationId}:${result}:${fingerprint}`
  if (delivered.has(key) || notifying.has(key)) return
  notifying.add(key)
  try {
    notification.open({
      key: `hot-update:${record.operationId}`,
      type: result === 'success' ? 'success' : result === 'failed' ? 'error' : 'warning',
      placement: 'topRight',
      top: 40,
      message: h(
        'span',
        {
          key,
          onVnodeMounted: () => {
            if (delivered.has(key)) return
            delivered.add(key)
            notifying.delete(key)
            const current = store?.record
            if (
              !current ||
              current.operationId !== record.operationId ||
              current.result !== result ||
              resultFingerprint(current) !== fingerprint
            )
              return
            void window.electronAPI
              .acknowledgeHotUpdateResult(record.operationId, result)
              .catch(warn)
          },
        },
        t(
          result === 'success'
            ? 'comp.backendUpdateSucceeded'
            : result === 'cancelled'
              ? 'comp.backendUpdateCancelled'
              : record.phase === 'download'
                ? 'comp.backendHotUpdateFailedDownload'
                : 'comp.backendHotUpdateFailed'
        )
      ),
      description: record.error,
      duration: result === 'failed' ? 0 : 5,
      ...(result === 'failed'
        ? {
            onClick: openRecovery,
            btn: () =>
              h(Button, { size: 'small', onClick: openRecovery }, () =>
                t('comp.backendHotUpdateDetails')
              ),
          }
        : {}),
    })
  } catch (error) {
    notifying.delete(key)
    warn(error)
  }
}

async function notifyCompletedSuccess(record: HotUpdateRecord, epoch: number): Promise<void> {
  if (!connectionSeen || hooks?.isConnected?.() === false) return
  if (!refreshedOperations.has(record.operationId)) {
    if ((await getBackendVersion()) === false) return
    await hooks?.refreshState()
  }
  if (
    epoch === generation &&
    hooks?.isConnected?.() !== false &&
    store?.record?.operationId === record.operationId &&
    store.record.result === 'success'
  )
    notifyResult(record)
}

async function restoreConnection(record: HotUpdateRecord, epoch: number): Promise<void> {
  if (connecting.has(record.operationId)) return
  connecting.add(record.operationId)
  let connected = false
  try {
    connected = await reconnectNow('后端热更新完成')
    if (epoch !== generation || store?.record?.operationId !== record.operationId) return
    if (connected) {
      if ((await getBackendVersion()) === false)
        throw new Error(t('comp.backendHotUpdateFailedConnection'))
      await hooks?.refreshState()
      connected = hooks?.isConnected?.() ?? connected
      connectionSeen = connected
      if (connected) refreshedOperations.add(record.operationId)
    }
  } catch (error) {
    connected = false
    warn(error)
  } finally {
    connecting.delete(record.operationId)
  }
  if (
    epoch !== generation ||
    store?.record?.operationId !== record.operationId ||
    store.record.phase !== 'connecting' ||
    store.record.result !== null
  )
    return
  try {
    const verified = await window.electronAPI.completeHotUpdateConnection(
      record.operationId,
      connected
    )
    if (
      !verified &&
      epoch === generation &&
      store?.record?.operationId === record.operationId &&
      store.record.result === null
    ) {
      store.retryError = t('comp.backendHotUpdateFailedConnection')
      store.recoveryVisible = true
    }
  } catch (error) {
    // IPC loss is not an install failure. Keep ownership and let the user retry safely.
    if (epoch === generation && store?.record?.operationId === record.operationId) {
      store.retryError = String(error)
      store.recoveryVisible = true
    }
    warn(error)
  }
}

function acceptRecord(record: HotUpdateRecord, epoch: number): void {
  if (epoch !== generation || !store) return
  mutation++
  store.record = record
  store.retryError = null
  if (
    record.phase === 'stopping' &&
    record.result === 'failed' &&
    'backendAvailable' in record &&
    record.backendAvailable === true
  ) {
    const wasBlocked = store.blocked
    store.blocked = false
    if (wasBlocked) hooks?.end('热更新失败，当前后端仍可用')
    notifyResult(record)
    return
  }
  if (record.phase === 'download') {
    const wasBlocked = store.blocked
    store.blocked = false
    if (record.result !== 'failed') store.recoveryVisible = false
    if (wasBlocked) hooks?.end('自动后端热更新暂缓')
    if (record.result) notifyResult(record)
    return
  }
  if (record.result !== 'success' && record.result !== 'cancelled') {
    store.blocked = true
    hooks?.begin('自动后端热更新')
  }
  if (record.result) {
    if (record.result === 'success' || record.result === 'cancelled') {
      store.blocked = false
      hooks?.end('自动后端热更新结束')
      store.recoveryVisible = false
    }
    if (record.result === 'success') void notifyCompletedSuccess(record, epoch).catch(warn)
    else notifyResult(record)
    return
  }
  if (record.phase === 'stopping') {
    void window.electronAPI.readyHotUpdateRestart(record.operationId).catch(error => {
      warn(error)
    })
  }
  if (record.phase === 'connecting') void restoreConnection(record, epoch)
}

/** Install the event listener before reading the durable main-process snapshot. */
export function initializeAutoBackendHotUpdate(lifecycleHooks: LifecycleHooks): void {
  if (disposeListeners || !window.electronAPI?.onHotUpdateState) return
  store = useBackendHotUpdateStore()
  hooks = lifecycleHooks
  store.blocked = true
  hooks.begin('读取后端热更新记录')
  connectionSeen = lifecycleHooks.isConnected?.() ?? false
  const epoch = ++generation
  const removeState = window.electronAPI.onHotUpdateState(record => acceptRecord(record, epoch))
  const removeConnected = onConnected(() => {
    connectionSeen = true
    const record = store?.record
    if (record?.result === 'success') {
      void notifyCompletedSuccess(record, epoch).catch(warn)
    }
  })
  disposeListeners = () => {
    removeState()
    removeConnected()
  }
  const initialMutation = mutation
  void window.electronAPI
    .getHotUpdateRecord()
    .then(record => {
      if (mutation !== initialMutation || epoch !== generation) return
      if (record) acceptRecord(record, epoch)
      else if (store) {
        store.record = null
        store.recoveryVisible = false
        store.blocked = false
        hooks?.end('没有待恢复的后端热更新')
      }
    })
    .catch(error => {
      if (epoch === generation && mutation === initialMutation && store) {
        store.blocked = false
        hooks?.end('读取后端热更新记录失败')
      }
      warn(error)
    })
}

export function disposeAutoBackendHotUpdate(): void {
  generation++
  disposeListeners?.()
  disposeListeners = undefined
  hooks = undefined
  connecting.clear()
  notifying.clear()
  refreshedOperations.clear()
  if (store) store.blocked = false
  store = undefined
}

export function useAutoBackendHotUpdate() {
  const state = useBackendHotUpdateStore()
  const refs = storeToRefs(state)
  const outcome = computed<RuntimeUpdateOutcome | null>(() => {
    const record = state.record
    if (!record || (record.result !== 'failed' && !state.retryError)) return null
    const supportRequired =
      record.retryable === false ||
      record.code === 'INTERNAL_ERROR' ||
      record.remediation?.includes('contact-support')
    return {
      success: false,
      phase:
        record.phase === 'connecting' || record.code === 'HOT_UPDATE_CONNECTION_FAILED'
          ? 'connection'
          : record.phase === 'stopping'
            ? 'shutdown'
            : record.phase === 'starting'
              ? 'restart'
              : 'bootstrap',
      error: state.retryError ?? record.error,
      code: record.code,
      logs: record.logs,
      remediation: record.remediation,
      retryable: record.retryable,
      supportRequired,
      retryActions:
        supportRequired || record.phase === 'download' || record.phase === 'stopping'
          ? []
          : ['dependencies-sync', 'dependencies-rebuild', 'repair'],
    }
  })
  async function retry(repairMode?: HotUpdateRepairMode): Promise<void> {
    if (state.retrying) return
    const epoch = generation
    const operationId = state.record?.operationId
    state.retrying = true
    state.retryError = null
    try {
      const accepted = await window.electronAPI.retryHotUpdate(repairMode)
      if (epoch !== generation || state.record?.operationId !== operationId) return
      if (!accepted) {
        state.retryError = t('comp.backendHotUpdateRetryDeferred')
        return
      }
      // An invoke response never proves the target was applied: only the next record can unlock.
      const mutationBeforeSnapshot = mutation
      const snapshot = await window.electronAPI.getHotUpdateRecord()
      if (snapshot && mutation === mutationBeforeSnapshot) acceptRecord(snapshot, epoch)
    } catch (error) {
      if (epoch === generation && state.record?.operationId === operationId)
        state.retryError = String(error)
      warn(error)
    } finally {
      state.retrying = false
    }
  }
  return { ...refs, outcome, retry, openRecovery }
}
