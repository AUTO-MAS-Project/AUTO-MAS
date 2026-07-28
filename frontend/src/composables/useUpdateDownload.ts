import { computed, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
import { connectionState, onConnected } from '@/services/websocket/connection'
import {
  WS_ID_UPDATE,
  WS_UPDATE_CANCELLED,
  WS_UPDATE_COMPLETED,
  WS_UPDATE_FAILED,
  WS_UPDATE_PROGRESS,
  type WSUpdateProgressData,
} from '@/services/websocket/types'
import { createLowSpeedDetector } from '@/composables/updateDownloadSpeed'
import { updateDownloadApi, type UpdateDownloadSnapshot } from '@/services/updateDownloadApi'

const logger = window.electronAPI.getLogger('更新下载状态')

const DOWNLOAD_TIMEOUT_MS = 2 * 60 * 60 * 1000

export type UpdateDownloadStatus =
  | 'idle'
  | 'downloading'
  | 'cancelling'
  | 'switchingSource'
  | 'completed'
  | 'failed'

export type UpdateDownloadProgress = WSUpdateProgressData

const status = ref<UpdateDownloadStatus>('idle')
const modalVisible = ref(false)
const source = ref('')
const downloadedSize = ref(0)
const fileSize = ref(0)
const speed = ref(0)
const failureReason = ref('')
const latestVersion = ref('')
const updateData = ref<Record<string, string[]>>({})

let subscriptionIds: string[] = []
let disposeConnectedListener: (() => void) | null = null
let snapshotGeneration = 0
let mutationGeneration = 0
let downloadTimeout: ReturnType<typeof setTimeout> | null = null
const lowSpeedDetector = createLowSpeedDetector()

const progressPercent = computed(() => {
  if (fileSize.value <= 0) return 0
  return Math.min((downloadedSize.value / fileSize.value) * 100, 100)
})

const sourceLabel = computed(() => {
  if (!source.value) return ''
  const labels: Record<string, string> = {
    GitHub: 'GitHub 源',
    CNB: 'CNB 源',
    MirrorChyan: 'Mirror 酱源',
    AutoSite: '自建源',
  }
  return labels[source.value] || source.value
})

const estimatedTimeRemaining = computed(() => {
  if (speed.value <= 0 || downloadedSize.value <= 0 || fileSize.value <= 0) return ''
  const remainingBytes = fileSize.value - downloadedSize.value
  const remainingSeconds = remainingBytes / speed.value

  if (remainingSeconds < 60) {
    return `${Math.ceil(remainingSeconds)}秒`
  }
  if (remainingSeconds < 3600) {
    const minutes = Math.floor(remainingSeconds / 60)
    const seconds = Math.ceil(remainingSeconds % 60)
    return `${minutes}分${seconds}秒`
  }

  const hours = Math.floor(remainingSeconds / 3600)
  const minutes = Math.floor((remainingSeconds % 3600) / 60)
  return `${hours}小时${minutes}分钟`
})

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const base = 1024
  const units = ['B', 'KB', 'MB', 'GB']
  const unitIndex = Math.floor(Math.log(bytes) / Math.log(base))
  return `${parseFloat((bytes / Math.pow(base, unitIndex)).toFixed(2))} ${units[unitIndex]}`
}

const formatSpeed = (bytesPerSecond: number) => {
  if (bytesPerSecond === 0) return '0 B/s'
  const base = 1024
  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
  const unitIndex = Math.floor(Math.log(bytesPerSecond) / Math.log(base))
  const value = bytesPerSecond / Math.pow(base, unitIndex)
  return `${parseFloat(value.toFixed(1))} ${units[unitIndex]}`
}

const stopRuntimeMonitoring = () => {
  if (downloadTimeout) {
    clearTimeout(downloadTimeout)
    downloadTimeout = null
  }
}

const ensureSubscription = () => {
  if (subscriptionIds.length > 0) return
  subscriptionIds = [
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_PROGRESS }, wsMessage =>
      receiveProgress(wsMessage.data)
    ),
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_CANCELLED }, () => receiveCancelled()),
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_COMPLETED }, () => receiveCompleted()),
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_FAILED }, wsMessage =>
      receiveFailed(wsMessage.data.message || '下载失败')
    ),
  ]
  logger.debug(`WebSocket 订阅已创建: ${subscriptionIds.join(', ')}`)
}

const startRuntimeMonitoring = () => {
  stopRuntimeMonitoring()

  downloadTimeout = setTimeout(() => {
    if (
      status.value === 'downloading' ||
      status.value === 'cancelling' ||
      status.value === 'switchingSource'
    ) {
      logger.warn('更新下载等待超时')
      status.value = 'failed'
      failureReason.value = '下载超时，请检查网络连接；后台任务可能仍在运行'
      speed.value = 0
      stopRuntimeMonitoring()
    }
  }, DOWNLOAD_TIMEOUT_MS)
}

const clearSubscription = () => {
  for (const subscriptionId of subscriptionIds) {
    unsubscribe(subscriptionId)
  }
  subscriptionIds = []
}

const resetState = () => {
  stopRuntimeMonitoring()
  status.value = 'idle'
  source.value = ''
  downloadedSize.value = 0
  fileSize.value = 0
  speed.value = 0
  failureReason.value = ''
  lowSpeedDetector.reset()
}

// 任何 WS 状态变更都比已发出的 HTTP 快照更新，使旧响应在返回时失效。
const invalidateSnapshot = (): number => {
  snapshotGeneration++
  mutationGeneration++
  return mutationGeneration
}

// 每个操作捕获自己的代次；较新的 WS/本地状态变更发生后，迟到的 HTTP 结果不得回滚它。
const isCurrentOperation = (generation: number): boolean => generation === mutationGeneration

const getActionErrorMessage = (error: unknown, fallback: string): string => {
  if (typeof error === 'object' && error !== null && 'body' in error) {
    const body = (error as { body?: unknown }).body
    if (typeof body === 'object' && body !== null && 'message' in body) {
      const bodyMessage = (body as { message?: unknown }).message
      if (typeof bodyMessage === 'string' && bodyMessage.trim()) return bodyMessage
    }
  }
  if (error instanceof Error && error.message.trim()) return error.message
  return fallback
}

const receiveProgress = (data: UpdateDownloadProgress) => {
  invalidateSnapshot()
  // WS progress 是较 HTTP action response 更新的权威状态；它也会令在途 action token 失效。
  status.value = 'downloading'
  downloadedSize.value = data.downloaded_size || 0
  fileSize.value = data.file_size || 0
  speed.value = data.speed || 0
  source.value = data.source || ''

  if (lowSpeedDetector.update(data.source, data.speed)) {
    Modal.confirm({
      title: `${sourceLabel.value || '当前来源'}下载速度较慢`,
      content: '下载速度已连续 10 秒低于 50 KB/s，是否切换至 CNB 源并重新下载？',
      okText: '切换至 CNB 源',
      cancelText: '继续下载',
      zIndex: 10001,
      centered: true,
      onOk: switchToCnb,
      onCancel: () => lowSpeedDetector.suppress(),
    })
  }
}

const receiveCancelled = () => {
  invalidateSnapshot()
  logger.info('下载已取消')
  resetState()
  modalVisible.value = false
}

const receiveCompleted = () => {
  invalidateSnapshot()
  logger.info('下载完成')
  stopRuntimeMonitoring()
  status.value = 'completed'
  speed.value = 0
}

const receiveFailed = (reason: string) => {
  invalidateSnapshot()
  logger.error(`下载失败: ${reason}`)
  stopRuntimeMonitoring()
  status.value = 'failed'
  failureReason.value = reason
  speed.value = 0
}

const applyDownloadSnapshot = (snapshot: UpdateDownloadSnapshot): void => {
  source.value = snapshot.source ?? ''
  downloadedSize.value = snapshot.downloaded_size ?? 0
  fileSize.value = snapshot.file_size ?? 0
  speed.value = snapshot.speed ?? 0
  if (snapshot.version) latestVersion.value = snapshot.version
  failureReason.value = snapshot.message ?? ''

  switch (snapshot.status) {
    case 'downloading':
      status.value = 'downloading'
      modalVisible.value = true
      startRuntimeMonitoring()
      break
    case 'switchingSource':
      status.value = 'switchingSource'
      modalVisible.value = true
      startRuntimeMonitoring()
      break
    case 'completed':
      stopRuntimeMonitoring()
      status.value = 'completed'
      speed.value = 0
      modalVisible.value = true
      break
    case 'failed':
      stopRuntimeMonitoring()
      status.value = 'failed'
      speed.value = 0
      failureReason.value = snapshot.message ?? '下载失败'
      modalVisible.value = true
      break
    case 'cancelled':
    case 'idle':
    default:
      resetState()
      modalVisible.value = false
      break
  }
}

export async function refreshUpdateDownloadSnapshot(): Promise<void> {
  const generation = ++snapshotGeneration
  try {
    const snapshot = await updateDownloadApi.status()
    if (generation !== snapshotGeneration) return
    applyDownloadSnapshot(snapshot)
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.warn(`读取更新下载 HTTP 快照失败: ${errorMessage}`)
  }
}

/** 在主连接建立前注册更新下载常驻订阅；幂等。 */
export function bootstrapUpdateDownloadSubscriptions(): void {
  ensureSubscription()
  if (!disposeConnectedListener) {
    disposeConnectedListener = onConnected(refreshUpdateDownloadSnapshot)
  }
  if (connectionState().value === 'open') void refreshUpdateDownloadSnapshot()
}

/** 应用最终退出时释放更新下载常驻资源；幂等。 */
export function disposeUpdateDownloadSubscriptions(): void {
  invalidateSnapshot()
  disposeConnectedListener?.()
  disposeConnectedListener = null
  clearSubscription()
  stopRuntimeMonitoring()
}

const start = async (version: string, data: Record<string, string[]>) => {
  logger.info(`开始下载: ${version}`)
  const operationGeneration = invalidateSnapshot()
  resetState()
  latestVersion.value = version
  updateData.value = data

  ensureSubscription()
  status.value = 'downloading'
  modalVisible.value = true
  startRuntimeMonitoring()

  try {
    const response = await Service.downloadUpdateApiUpdateDownloadPost(version || undefined)
    if (!isCurrentOperation(operationGeneration)) return
    if (response.code !== 200) {
      receiveFailed(response.message || '下载请求失败')
      return
    }
    invalidateSnapshot()
  } catch (error) {
    if (!isCurrentOperation(operationGeneration)) return
    const errorMessage = getActionErrorMessage(error, '网络请求失败，请检查网络连接')
    logger.error(`启动下载失败: ${errorMessage}`)
    receiveFailed(errorMessage)
  }
}
const cancel = async () => {
  if (status.value !== 'downloading') return

  const operationGeneration = invalidateSnapshot()
  status.value = 'cancelling'
  try {
    const response = await updateDownloadApi.cancel()
    if (!isCurrentOperation(operationGeneration)) return
    if (response.code === 200) {
      message.success('下载已取消')
      receiveCancelled()
    } else {
      message.error(response.message || '取消下载失败')
      invalidateSnapshot()
      status.value = 'downloading'
    }
  } catch (error) {
    if (!isCurrentOperation(operationGeneration)) return
    const errorMessage = getActionErrorMessage(error, '取消下载失败')
    logger.error(`取消下载失败: ${errorMessage}`)
    message.error(errorMessage)
    invalidateSnapshot()
    status.value = 'downloading'
  }
}

const background = () => {
  modalVisible.value = false
}

const open = () => {
  if (status.value !== 'idle') {
    modalVisible.value = true
  }
}

const switchToCnb = async () => {
  if (status.value !== 'downloading') return

  const operationGeneration = invalidateSnapshot()
  status.value = 'switchingSource'
  try {
    const response = await updateDownloadApi.switchToCnb()
    if (!isCurrentOperation(operationGeneration)) return
    if (response.code === 200) {
      invalidateSnapshot()
      source.value = 'CNB'
      status.value = 'downloading'
      lowSpeedDetector.reset()
      startRuntimeMonitoring()
    } else {
      const failureMessage = response.message || '切换下载源失败'
      message.error(failureMessage)
      receiveFailed(failureMessage)
    }
  } catch (error) {
    if (!isCurrentOperation(operationGeneration)) return
    const errorMessage = getActionErrorMessage(error, '切换下载源失败')
    logger.error(`切换下载源失败: ${errorMessage}`)
    message.error(errorMessage)
    receiveFailed(errorMessage)
  }
}

const retry = async () => {
  await start(latestVersion.value, updateData.value)
}

const install = async () => {
  try {
    const response = await Service.installUpdateApiUpdateInstallPost()
    if (response.code === 200) {
      message.success('安装程序已启动')
      resetState()
      modalVisible.value = false
    } else {
      message.error(response.message || '启动安装失败')
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(`安装失败: ${errorMessage}`)
    message.error('启动安装失败')
  }
}

const installLater = () => {
  modalVisible.value = false
}

const reset = () => {
  invalidateSnapshot()
  resetState()
  modalVisible.value = false
}

export function useUpdateDownload() {
  return {
    status,
    modalVisible,
    source,
    sourceLabel,
    downloadedSize,
    fileSize,
    speed,
    progressPercent,
    estimatedTimeRemaining,
    failureReason,
    latestVersion,
    updateData,
    formatBytes,
    formatSpeed,
    start,
    cancel,
    background,
    open,
    switchToCnb,
    retry,
    install,
    installLater,
    reset,
    bootstrapUpdateDownloadSubscriptions,
    refreshUpdateDownloadSnapshot,
    disposeUpdateDownloadSubscriptions,
    receiveProgress,
    receiveCancelled,
    receiveCompleted,
    receiveFailed,
  }
}
