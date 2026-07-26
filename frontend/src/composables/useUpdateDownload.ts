import { computed, ref } from 'vue'
import { Modal, message } from 'ant-design-vue'
import { Service } from '@/api/services/Service'
import { subscribe, unsubscribe, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import { createLowSpeedDetector } from '@/composables/updateDownloadSpeed'
import { updateDownloadApi } from '@/services/updateDownloadApi'
import {
  WS_ID_UPDATE,
  WS_UPDATE_CANCELLED,
  WS_UPDATE_COMPLETED,
  WS_UPDATE_FAILED,
  WS_UPDATE_INSTALLING,
  WS_UPDATE_PROGRESS,
  WS_UPDATE_VERIFYING,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('更新下载状态')

const DOWNLOAD_TIMEOUT_MS = 2 * 60 * 60 * 1000
const INSTALL_PREPARATION_TIMEOUT_MS = 5 * 60 * 1000
const SUBSCRIPTION_HEALTH_CHECK_MS = 3_000

/**
 * 更新流程状态机。
 *
 * 状态流：
 *   idle → downloading → completed → verifying → installing → 应用退出
 *                    ↘             ↘            ↘
 *                     failed        failed       failed
 *
 * - completed：更新包下载完成，等待用户点击安装；不代表已完成内容校验
 * - verifying：后端正在校验更新包完整性（SHA256 摘要比对）
 * - installing：后端正在解压并启动安装程序；成功后应用会退出
 * - failed：任何阶段失败，保留诊断信息供复制
 */
export type UpdateDownloadStatus =
  | 'idle'
  | 'downloading'
  | 'cancelling'
  | 'switchingSource'
  | 'completed'
  | 'verifying'
  | 'installing'
  | 'failed'

export interface UpdateDownloadProgress {
  downloaded_size: number
  file_size: number
  speed: number
  source: string
}

export interface UpdateDownloadSignal {
  Cancelled?: boolean
  Accomplish?: string
  Failed?: string
}

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
let downloadTimeout: ReturnType<typeof setTimeout> | null = null
let installTimeout: ReturnType<typeof setTimeout> | null = null
let subscriptionHealthCheck: ReturnType<typeof setInterval> | null = null
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
  if (installTimeout) {
    clearTimeout(installTimeout)
    installTimeout = null
  }
  if (subscriptionHealthCheck) {
    clearInterval(subscriptionHealthCheck)
    subscriptionHealthCheck = null
  }
}

const ensureSubscription = () => {
  if (subscriptionIds.length > 0) return
  subscriptionIds = [
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_PROGRESS }, handleMessage),
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_COMPLETED }, handleMessage),
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_VERIFYING }, handleMessage),
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_INSTALLING }, handleMessage),
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_FAILED }, handleMessage),
    subscribe({ id: WS_ID_UPDATE, type: WS_UPDATE_CANCELLED }, handleMessage),
    // 迁移期兼容旧后端。
    subscribe({ id: WS_ID_UPDATE, type: 'Update' }, handleMessage),
    subscribe({ id: WS_ID_UPDATE, type: 'Signal' }, handleMessage),
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

  subscriptionHealthCheck = setInterval(() => {
    if (subscriptionIds.length === 0) {
      logger.warn('更新下载订阅丢失，正在重新建立')
      ensureSubscription()
    }
  }, SUBSCRIPTION_HEALTH_CHECK_MS)
}

const clearSubscription = () => {
  for (const subscriptionId of subscriptionIds) unsubscribe(subscriptionId)
  subscriptionIds = []
}

const resetState = () => {
  stopRuntimeMonitoring()
  clearSubscription()
  status.value = 'idle'
  source.value = ''
  downloadedSize.value = 0
  fileSize.value = 0
  speed.value = 0
  failureReason.value = ''
  lowSpeedDetector.reset()
}

const receiveProgress = (data: UpdateDownloadProgress) => {
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

const receiveSignal = (data: UpdateDownloadSignal) => {
  if (data.Cancelled) {
    logger.info('下载已取消')
    resetState()
    modalVisible.value = false
    return
  }

  if (data.Accomplish) {
    logger.info('更新包下载完成，等待用户确认安装')
    stopRuntimeMonitoring()
    status.value = 'completed'
    speed.value = 0
    return
  }

  if (data.Failed) {
    logger.error(`下载失败: ${data.Failed}`)
    stopRuntimeMonitoring()
    status.value = 'failed'
    failureReason.value = data.Failed
    speed.value = 0
  }
}

/**
 * Lane 8：诊断信息，用于失败时复制到剪贴板。
 *
 * 包含：版本、下载源、已下载大小、文件总大小、失败原因、时间戳。
 * 在 failed 状态下用户可点击"复制诊断信息"按钮获取。
 */
const diagnosticInfo = computed(() => {
  const lines = [
    `=== AUTO-MAS 更新诊断信息 ===`,
    `时间: ${new Date().toISOString()}`,
    `目标版本: ${latestVersion.value || '未知'}`,
    `当前状态: ${status.value}`,
    `下载源: ${source.value || sourceLabel.value || '未知'}`,
    `已下载: ${formatBytes(downloadedSize.value)} / ${formatBytes(fileSize.value)}`,
    `失败原因: ${failureReason.value || '无'}`,
    `========================`,
  ]
  return lines.join('\n')
})

const copyDiagnostic = async () => {
  try {
    await navigator.clipboard.writeText(diagnosticInfo.value)
    message.success('诊断信息已复制到剪贴板')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制诊断信息失败: ${errorMsg}`)
    message.error('复制失败，请手动选择文本复制')
  }
}

function handleMessage(wsMessage: WebSocketBaseMessage) {
  if (wsMessage.id !== 'Update') return

  if (wsMessage.type === WS_UPDATE_PROGRESS || wsMessage.type === 'Update') {
    receiveProgress(wsMessage.data as UpdateDownloadProgress)
  } else if (wsMessage.type === WS_UPDATE_COMPLETED) {
    receiveSignal({ Accomplish: String((wsMessage.data as { file?: unknown }).file ?? '') })
  } else if (wsMessage.type === WS_UPDATE_VERIFYING) {
    // Lane 01：后端进入完整性校验阶段
    status.value = 'verifying'
    logger.info(
      `正在校验更新包完整性 (job: ${(wsMessage.data as { job_id?: unknown }).job_id ?? '?'})`
    )
  } else if (wsMessage.type === WS_UPDATE_INSTALLING) {
    // Lane 01：后端校验通过，开始解压安装
    status.value = 'installing'
    failureReason.value = ''
    logger.info(`正在安装更新 (job: ${(wsMessage.data as { job_id?: unknown }).job_id ?? '?'})`)
  } else if (wsMessage.type === WS_UPDATE_FAILED) {
    receiveSignal({ Failed: String((wsMessage.data as { message?: unknown }).message ?? '') })
  } else if (wsMessage.type === WS_UPDATE_CANCELLED) {
    receiveSignal({ Cancelled: true })
  } else if (wsMessage.type === 'Signal') {
    receiveSignal(wsMessage.data as UpdateDownloadSignal)
  }
}

const start = async (version: string, data: Record<string, string[]>) => {
  logger.info(`开始下载: ${version}`)
  resetState()
  latestVersion.value = version
  updateData.value = data

  ensureSubscription()

  try {
    const response = await Service.downloadUpdateApiUpdateDownloadPost(version || undefined)
    if (response.code !== 200) {
      status.value = 'failed'
      failureReason.value = response.message || '下载请求失败'
      return
    }
    status.value = 'downloading'
    modalVisible.value = true
    startRuntimeMonitoring()
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(`启动下载失败: ${errorMessage}`)
    status.value = 'failed'
    failureReason.value = '网络请求失败，请检查网络连接'
  }
}
const cancel = async () => {
  if (status.value !== 'downloading') return

  status.value = 'cancelling'
  try {
    const response = await updateDownloadApi.cancel()
    if (response.code === 200) {
      message.success('下载已取消')
      resetState()
      modalVisible.value = false
    } else {
      message.error(response.message || '取消下载失败')
      status.value = 'downloading'
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(`取消下载失败: ${errorMessage}`)
    message.error('取消下载失败')
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

  status.value = 'switchingSource'
  try {
    const response = await updateDownloadApi.switchToCnb()
    if (response.code === 200) {
      source.value = 'CNB'
      status.value = 'downloading'
      lowSpeedDetector.reset()
      startRuntimeMonitoring()
    } else {
      message.error(response.message || '切换下载源失败')
      stopRuntimeMonitoring()
      status.value = 'failed'
      failureReason.value = response.message || '切换下载源失败'
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(`切换下载源失败: ${errorMessage}`)
    message.error('切换下载源失败')
    stopRuntimeMonitoring()
    status.value = 'failed'
    failureReason.value = errorMessage
  }
}

const retry = async () => {
  await start(latestVersion.value, updateData.value)
}

const install = async () => {
  if (status.value !== 'completed') return

  try {
    // Lane 01：安装请求发送后进入 verifying 状态，等待后端 WS 事件流
    status.value = 'verifying'
    failureReason.value = ''
    const response = await Service.installUpdateApiUpdateInstallPost()
    if (response.code === 200) {
      // HTTP 200 只表示后端安装任务已成功排队。后端随后校验摘要、
      // 解压更新包，并通过 WS 推送 verifying → installing → failed 事件。
      // 安装成功后后端会直接退出应用。
      installTimeout = setTimeout(() => {
        if (status.value !== 'verifying' && status.value !== 'installing') return
        status.value = 'failed'
        failureReason.value = '安装准备超时，请查看后端日志；安装任务可能仍在运行'
        stopRuntimeMonitoring()
      }, INSTALL_PREPARATION_TIMEOUT_MS)
    } else {
      message.error(response.message || '启动安装失败')
      status.value = 'failed'
      failureReason.value = response.message || '启动安装失败'
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(`安装失败: ${errorMessage}`)
    message.error('启动安装失败')
    status.value = 'failed'
    failureReason.value = errorMessage
  }
}

const installLater = () => {
  modalVisible.value = false
}

const reset = () => {
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
    diagnosticInfo,
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
    copyDiagnostic,
    receiveProgress,
    receiveSignal,
  }
}
