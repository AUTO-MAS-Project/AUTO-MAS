import { translate as t } from '@/i18n'
import { computed, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { connectionState, onConnected } from '@/services/websocket/connection'
import type { WSUpdateProgressData } from '@/services/websocket/types'
import { createLowSpeedDetector } from '@/composables/updateDownloadSpeed'
import { formatBytes, formatSpeed } from '@/utils/byteFormat'
import { updateDownloadApi, type UpdateDownloadSnapshot } from '@/services/updateDownloadApi'
import type { ChangelogData } from '@/utils/changelog'
import { beginAnalyticsOperation } from '@/utils/analytics'
import { analyticsUpdateSource, beginDownloadAnalytics } from '@/utils/updateAnalytics'
import type { AnalyticsEventProps } from '@/types/analytics'

const logger = window.electronAPI.getLogger('更新下载状态')

const DOWNLOAD_TIMEOUT_MS = 2 * 60 * 60 * 1000

export type UpdateDownloadStatus =
  | 'idle'
  | 'downloading'
  | 'cancelling'
  | 'switchingSource'
  | 'completed'
  | 'failed'

type UpdateDownloadProgress = WSUpdateProgressData

const status = ref<UpdateDownloadStatus>('idle')
const modalVisible = ref(false)
const source = ref('')
const downloadedSize = ref(0)
const fileSize = ref(0)
const speed = ref(0)
const failureReason = ref('')
const latestVersion = ref('')
const updateData = ref<ChangelogData>({})

let disposeUpdateEvents: (() => void) | null = null
let disposeConnectedListener: (() => void) | null = null
let snapshotGeneration = 0
let mutationGeneration = 0
let downloadTimeout: ReturnType<typeof setTimeout> | null = null
const lowSpeedDetector = createLowSpeedDetector()
let downloadAnalytics: ReturnType<typeof beginDownloadAnalytics> | null = null

const finishDownloadAnalytics = (
  outcome: AnalyticsEventProps['update_download_finished']['outcome']
) => {
  const operation = downloadAnalytics
  downloadAnalytics = null
  operation?.finish(source.value, outcome)
}

const progressPercent = computed(() => {
  if (fileSize.value <= 0) return 0
  return Math.min((downloadedSize.value / fileSize.value) * 100, 100)
})

const sourceLabel = computed(() => {
  if (!source.value) return ''
  const labels: Record<string, string> = {
    GitHub: t('bootstrap.comp.sourceGithub'),
    CNB: t('bootstrap.comp.sourceCnb'),
    MirrorChyan: t('bootstrap.comp.sourceMirror'),
    AutoSite: t('bootstrap.comp.sourceCustom'),
  }
  return labels[source.value] || source.value
})

const downloadHint = computed(() => {
  if (status.value === 'completed') return t('bootstrap.comp.downloadReady')
  if (status.value === 'switchingSource') return t('bootstrap.comp.downloadSwitching')
  if (status.value === 'cancelling') return t('bootstrap.comp.downloadCancelling')
  if (status.value === 'failed') return t('bootstrap.comp.downloadFailed')
  if (status.value === 'downloading') {
    const source = sourceLabel.value
      ? t('bootstrap.comp.downloadSource', { source: sourceLabel.value })
      : ''
    return t('bootstrap.comp.downloading', { source, progress: progressPercent.value.toFixed(1) })
  }
  return ''
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

const stopRuntimeMonitoring = () => {
  if (downloadTimeout) {
    clearTimeout(downloadTimeout)
    downloadTimeout = null
  }
}

const ensureSubscription = () => {
  // 按需建立唯一的桌面更新事件订阅，避免多个调用者重复监听同一下载。
  if (disposeUpdateEvents) return
  disposeUpdateEvents = window.electronAPI.onAppUpdate(event => {
    // 把主进程更新快照分派到完成、取消、失败或进度处理，并同步实际下载来源。
    const snapshot = event.snapshot
    source.value = snapshot.source ?? ''
    if (event.type === 'completed') receiveCompleted()
    else if (event.type === 'cancelled') receiveCancelled()
    else if (event.type === 'failed') receiveFailed(snapshot.message || '下载失败')
    else
      receiveProgress({
        downloaded_size: snapshot.downloaded_size,
        file_size: snapshot.file_size,
        speed: snapshot.speed,
        source: snapshot.source ?? '',
      })
  })
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
      finishDownloadAnalytics('observation_unknown')
      status.value = 'failed'
      failureReason.value = '下载超时，请检查网络连接；后台任务可能仍在运行'
      speed.value = 0
      stopRuntimeMonitoring()
    }
  }, DOWNLOAD_TIMEOUT_MS)
}

const clearSubscription = () => {
  // 解除桌面更新事件订阅并清空释放函数，允许后续重新订阅。
  disposeUpdateEvents?.()
  disposeUpdateEvents = null
}

const resetState = () => {
  downloadAnalytics = null
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
  downloadAnalytics?.started(source.value)

  if (lowSpeedDetector.update(data.source, data.speed)) {
    Modal.confirm({
      title: t('bootstrap.comp.downloadSlow', {
        source: sourceLabel.value || t('bootstrap.comp.currentSource'),
      }),
      content: t('bootstrap.misc.downloadHasBeenUnder'),
      okText: t('bootstrap.misc.switchCnbSource'),
      cancelText: t('bootstrap.misc.continueDownload'),
      zIndex: 10001,
      centered: true,
      onOk: () => switchDownloadSource('low_speed'),
      onCancel: () => lowSpeedDetector.suppress(),
    })
  }
}

const receiveCancelled = () => {
  finishDownloadAnalytics('cancelled')
  invalidateSnapshot()
  logger.info('下载已取消')
  resetState()
  modalVisible.value = false
}

const receiveCompleted = () => {
  finishDownloadAnalytics('completed')
  invalidateSnapshot()
  logger.info('下载完成')
  stopRuntimeMonitoring()
  status.value = 'completed'
  speed.value = 0
}

const receiveFailed = (reason: string, outcome: 'failed' | 'observation_unknown' = 'failed') => {
  finishDownloadAnalytics(outcome)
  invalidateSnapshot()
  logger.error(`下载失败: ${reason}`)
  stopRuntimeMonitoring()
  // 后台下载（窗口已收起）中断时没有入口展示原因，立即重新打开下载窗口
  const reopenModal =
    !modalVisible.value &&
    (status.value === 'downloading' ||
      status.value === 'cancelling' ||
      status.value === 'switchingSource')
  status.value = 'failed'
  failureReason.value = reason
  speed.value = 0
  if (reopenModal) modalVisible.value = true
}

const applyDownloadSnapshot = (snapshot: UpdateDownloadSnapshot): void => {
  // 快照用于对账，终态快照也不伪造成新收到的完成事件。
  if (!['downloading', 'switchingSource'].includes(snapshot.status)) downloadAnalytics = null
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

async function refreshUpdateDownloadSnapshot(): Promise<void> {
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
  downloadAnalytics = null
  invalidateSnapshot()
  disposeConnectedListener?.()
  disposeConnectedListener = null
  clearSubscription()
  stopRuntimeMonitoring()
}

const start = async (version: string, data: ChangelogData, downloader?: 'builtin' | 'fluxdown') => {
  // 初始化本次版本下载的界面和观测状态，订阅主进程事件后提交下载，并隔离过期响应。
  logger.info(`开始下载: ${version}${downloader ? ` (指定下载器: ${downloader})` : ''}`)
  const operationGeneration = invalidateSnapshot()
  resetState()
  const attempt = beginDownloadAnalytics(version)
  downloadAnalytics = attempt
  latestVersion.value = version
  updateData.value = data

  ensureSubscription()
  status.value = 'downloading'
  modalVisible.value = true
  startRuntimeMonitoring()

  try {
    const response = await updateDownloadApi.start(version, downloader)
    if (downloadAnalytics === attempt) attempt.started(source.value)
    if (!isCurrentOperation(operationGeneration)) return
    if (response.code !== 200) {
      receiveFailed(response.message || '下载请求失败')
      return
    }
    invalidateSnapshot()
  } catch (error) {
    if (downloadAnalytics === attempt) attempt.started(source.value)
    if (!isCurrentOperation(operationGeneration)) return
    const errorMessage = getActionErrorMessage(error, '网络请求失败，请检查网络连接')
    logger.error(`启动下载失败: ${errorMessage}`)
    receiveFailed(errorMessage, 'observation_unknown')
  }
}
// 取消失败时后端不一定还在下载（可能已广播失败/完成，或压根没有活动任务），
// 不再臆测回「下载中」，而是以 HTTP 快照为准；快照也读不到时才退回下载中。
const settleCancelFailure = async (): Promise<void> => {
  invalidateSnapshot()
  await refreshUpdateDownloadSnapshot()
  if (status.value === 'cancelling') status.value = 'downloading'
}

const cancel = async () => {
  if (status.value !== 'downloading') return

  const operationGeneration = invalidateSnapshot()
  status.value = 'cancelling'
  try {
    const response = await updateDownloadApi.cancel()
    if (!isCurrentOperation(operationGeneration)) return
    if (response.code === 200) {
      message.success(t('bootstrap.misc.downloadCancelled'))
      receiveCancelled()
    } else {
      message.error(response.message || '取消下载失败')
      await settleCancelFailure()
    }
  } catch (error) {
    if (!isCurrentOperation(operationGeneration)) return
    const errorMessage = getActionErrorMessage(error, '取消下载失败')
    logger.error(`取消下载失败: ${errorMessage}`)
    message.error(errorMessage)
    await settleCancelFailure()
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

const switchToCnb = () => switchDownloadSource('manual')

const switchDownloadSource = async (trigger_kind: 'manual' | 'low_speed') => {
  if (status.value !== 'downloading') return
  const operation = beginAnalyticsOperation('update_source_changed')
  const dimensions = {
    from_kind: analyticsUpdateSource(source.value),
    to_kind: 'cnb' as const,
    trigger_kind,
  }

  const operationGeneration = invalidateSnapshot()
  status.value = 'switchingSource'
  try {
    const response = await updateDownloadApi.switchToCnb()
    operation.finish({ ...dimensions, outcome: response.code === 200 ? 'success' : 'failure' })
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
      receiveFailed(failureMessage, 'observation_unknown')
    }
  } catch (error) {
    operation.finish({ ...dimensions, outcome: 'unknown' })
    if (!isCurrentOperation(operationGeneration)) return
    const errorMessage = getActionErrorMessage(error, '切换下载源失败')
    logger.error(`切换下载源失败: ${errorMessage}`)
    message.error(errorMessage)
    receiveFailed(errorMessage, 'observation_unknown')
  }
}

const retry = async () => {
  await start(latestVersion.value, updateData.value)
}

/** 多次失败后在失败弹窗里给用户的显式选择：改用内置 httpx 重新下载 */
const retryWithBuiltin = async () => {
  await start(latestVersion.value, updateData.value, 'builtin')
}

const install = async () => {
  // 请求桌面主进程安装已准备更新包，记录请求是否受理并在成功启动安装器后关闭下载界面。
  const operation = beginAnalyticsOperation('update_install_requested')
  try {
    const response = await updateDownloadApi.install()
    operation.finish({
      choice: 'install_now',
      request_outcome: response.code === 200 ? 'accepted' : 'rejected',
    })
    if (response.code === 200) {
      message.success(t('bootstrap.misc.installerStarted'))
      resetState()
      modalVisible.value = false
    } else {
      message.error(response.message || '启动安装失败')
    }
  } catch (error) {
    operation.finish({ choice: 'install_now', request_outcome: 'unknown' })
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(`安装失败: ${errorMessage}`)
    message.error(t('bootstrap.misc.couldNotStartInstaller'))
  }
}

const installLater = () => {
  beginAnalyticsOperation('update_install_requested').finish({
    choice: 'later',
    request_outcome: 'not_requested',
  })
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
    downloadHint,
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
    retryWithBuiltin,
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
