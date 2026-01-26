<template>
  <a-modal v-model:open="visible" :title="`下载更新 ${latestVersion}`" :width="600" :footer="null" :mask-closable="false"
    :closable="false" :z-index="9999" class="update-download-modal" centered>
    <div class="download-container">
      <!-- 下载进度区域 -->
      <div v-if="isDownloading" class="download-progress-section">
        <!-- 主进度显示 -->
        <div class="main-progress">
          <div class="progress-header">
            <div class="progress-title">
              <a-spin :spinning="true" size="small" />
              <span class="download-title">下载进度</span>
            </div>
            <div class="progress-percent" :class="{
              'animate-pulse': downloadProgressPercent > 0 && downloadProgressPercent < 100,
            }">
              {{ downloadProgressPercent.toFixed(1) }}%
            </div>
          </div>

          <a-progress :percent="downloadProgressPercent" :show-info="false" stroke-color="var(--ant-color-primary)"
            trail-color="var(--ant-color-fill-secondary)" :stroke-width="8" class="progress-bar" />

          <!-- 进度信息行 -->
          <div class="progress-info-row">
            <div class="left-info">
              <span class="file-progress">{{ formatBytes(downloadProgress.downloaded_size) }} /
                {{ formatBytes(downloadProgress.file_size) }}</span>
              <span class="download-speed">{{ formatSpeed(downloadProgress.speed) }}</span>
            </div>
            <div v-if="estimatedTimeRemaining" class="right-info">
              <span class="eta-label">预计剩余时间</span>
              <span class="eta-value">{{ estimatedTimeRemaining }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 下载失败区域 -->
      <div v-if="downloadFailed" class="download-failed-section">
        <div class="failed-icon">
          <a-result status="error" title="下载失败" :sub-title="failureReason">
            <template #extra>
              <div class="failed-actions">
                <a-button type="primary" :loading="isRetrying" @click="handleRetry">
                  重试下载
                </a-button>
                <a-button @click="handleCancel"> 取消 </a-button>
              </div>
            </template>
          </a-result>
        </div>
      </div>

      <!-- 下载成功区域 -->
      <div v-if="downloadCompleted" class="download-success-section">
        <a-result status="success" title="下载完成" sub-title="更新包已下载完成，是否立即安装？">
          <template #extra>
            <div class="success-actions">
              <a-button type="primary" :loading="isInstalling" @click="handleInstall">
                立即安装
              </a-button>
              <a-button @click="handleLater"> 稍后安装 </a-button>
            </div>
          </template>
        </a-result>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { Service } from '@/api/services/Service.ts'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
const logger = window.electronAPI.getLogger('更新下载模态框')

// Props 定义
interface Props {
  visible: boolean
  latestVersion: string
  updateData: Record<string, string[]>
}

const props = defineProps<Props>()

// Emits 定义
const emit = defineEmits<{
  'update:visible': [value: boolean]
  completed: []
  cancelled: []
  installRequested: []
}>()

// WebSocket 相关
let updateSubscriptionId: string = ''

// 状态管理
const isDownloading = ref(false)
const downloadFailed = ref(false)
const downloadCompleted = ref(false)
const isRetrying = ref(false)
const isInstalling = ref(false)
const failureReason = ref('')

// WebSocket健康检查
let wsHealthCheckInterval: NodeJS.Timeout | null = null

// 下载超时定时器
let downloadTimeout: NodeJS.Timeout | null = null

// 下载进度相关状态
const downloadProgress = ref({
  downloaded_size: 0,
  file_size: 0,
  speed: 0,
})

// 计算下载进度百分比
const downloadProgressPercent = computed(() => {
  const progress = downloadProgress.value
  if (!progress.file_size || progress.file_size <= 0) {
    return 0
  }
  const percent = (progress.downloaded_size / progress.file_size) * 100
  return Math.min(percent, 100)
})

// 计算剩余时间
const estimatedTimeRemaining = computed(() => {
  const progress = downloadProgress.value
  const speed = progress.speed

  if (speed <= 0 || progress.downloaded_size <= 0 || progress.file_size <= 0) {
    return ''
  }

  const remainingBytes = progress.file_size - progress.downloaded_size
  const remainingSeconds = remainingBytes / speed

  if (remainingSeconds < 60) {
    return `${Math.ceil(remainingSeconds)}秒`
  } else if (remainingSeconds < 3600) {
    const minutes = Math.floor(remainingSeconds / 60)
    const seconds = Math.ceil(remainingSeconds % 60)
    return `${minutes}分${seconds}秒`
  } else {
    const hours = Math.floor(remainingSeconds / 3600)
    const minutes = Math.floor((remainingSeconds % 3600) / 60)
    return `${hours}小时${minutes}分钟`
  }
})

// 计算属性 - 响应式地接收外部 visible 状态
const visible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

// 格式化字节大小
const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 格式化速度
const formatSpeed = (bytesPerSecond: number) => {
  if (bytesPerSecond === 0) return '0 B/s'

  const k = 1024
  const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s']
  const i = Math.floor(Math.log(bytesPerSecond) / Math.log(k))
  const value = bytesPerSecond / Math.pow(k, i)

  return parseFloat(value.toFixed(1)) + ' ' + sizes[i]
}

// 重置状态
const resetState = () => {
  // 清除下载超时
  if (downloadTimeout) {
    clearTimeout(downloadTimeout)
    downloadTimeout = null
  }

  // 停止WebSocket健康检查
  stopWebSocketHealthCheck()

  isDownloading.value = false
  downloadFailed.value = false
  downloadCompleted.value = false
  isRetrying.value = false
  isInstalling.value = false
  failureReason.value = ''
  downloadProgress.value = {
    downloaded_size: 0,
    file_size: 0,
    speed: 0,
  }
}

// 开始下载
const startDownload = async () => {
  logger.info('开始下载流程')

  // 确保WebSocket订阅已建立
  ensureWebSocketSubscription()

  // 验证WebSocket连接状态
  logger.info('WebSocket连接准备就绪，开始下载...')

  resetState()
  isDownloading.value = true

  try {
    // 确保有版本信息，如果没有则先检查更新
    if (!props.latestVersion) {
      logger.info('没有版本信息，先检查更新')
      const checkResult = await Service.checkUpdateApiUpdateCheckPost({
        current_version: (import.meta as any).env?.VITE_APP_VERSION || '1.0.0',
        if_force: false,
      })

      if (checkResult.code !== 200 || !checkResult.if_need_update) {
        downloadFailed.value = true
        isDownloading.value = false
        failureReason.value = '无法获取更新信息，请先检查更新'
        return
      }
    }

    logger.info('调用下载API')
    const res = await Service.downloadUpdateApiUpdateDownloadPost()
    logger.debug('API响应:', res)

    if (res.code !== 200) {
      logger.error('下载请求失败:', res.message)
      downloadFailed.value = true
      isDownloading.value = false
      failureReason.value = res.message || '下载请求失败'
    } else {
      logger.info('下载请求成功，等待WebSocket进度更新')

      // 启动WebSocket健康检查
      startWebSocketHealthCheck()

      // 设置下载超时（2小时）
      downloadTimeout = setTimeout(
        () => {
          if (isDownloading.value) {
            logger.warn('下载超时，取消WebSocket订阅')
            isDownloading.value = false
            downloadFailed.value = true
            failureReason.value = '下载超时，请检查网络连接或稍后重试'
            stopWebSocketHealthCheck()
            cancelWebSocketSubscription()
          }
        },
        2 * 60 * 60 * 1000
      )
    }
  } catch (err) {
    logger.error('启动下载失败:', err)
    downloadFailed.value = true
    isDownloading.value = false
    failureReason.value = '网络请求失败，请检查网络连接'
    stopWebSocketHealthCheck()
    cancelWebSocketSubscription()
  }
}

// 重试下载
const handleRetry = async () => {
  isRetrying.value = true
  try {
    await startDownload()
  } finally {
    isRetrying.value = false
  }
}

// 取消
const handleCancel = () => {
  visible.value = false
  emit('cancelled')
}

// 稍后安装
const handleLater = () => {
  visible.value = false
  emit('completed')
}

// 立即安装
const handleInstall = async () => {
  isInstalling.value = true
  try {
    const res = await Service.installUpdateApiUpdateInstallPost()
    if (res.code === 200) {
      message.success('安装程序已启动')
      visible.value = false
      emit('installRequested')
    } else {
      message.error(res.message || '启动安装失败')
    }
  } catch (err) {
    logger.error('安装失败:', err)
    message.error('启动安装失败')
  } finally {
    isInstalling.value = false
  }
}

// WebSocket 消息处理
const handleUpdateMessage = (wsMessage: any) => {

  if (wsMessage.id === 'Update') {
    if (wsMessage.type === 'Update') {
      // 更新下载进度
      logger.debug('更新下载进度:', wsMessage.data)
      const { downloaded_size, file_size, speed } = wsMessage.data

      // 使用Object.assign确保响应式更新
      Object.assign(downloadProgress.value, {
        downloaded_size: downloaded_size || 0,
        file_size: file_size || 0,
        speed: speed || 0,
      })

      // 强制触发Vue的响应式更新
      nextTick(() => {
        logger.debug('进度更新后状态:', {
          进度: downloadProgress.value,
          百分比: downloadProgressPercent.value.toFixed(2) + '%',
          正在下载: isDownloading.value,
          订阅ID: updateSubscriptionId,
          时间戳: new Date().toISOString(),
        })
      })
    } else if (wsMessage.type === 'Signal') {
      logger.debug('收到Signal消息:', wsMessage.data)

      // 清除下载超时
      if (downloadTimeout) {
        clearTimeout(downloadTimeout)
        downloadTimeout = null
      }

      if (wsMessage.data.Accomplish) {
        // 下载完成 - 取消WebSocket订阅
        logger.info('下载完成，取消WebSocket订阅')
        isDownloading.value = false
        downloadCompleted.value = true
        stopWebSocketHealthCheck()
        cancelWebSocketSubscription()
      } else if (wsMessage.data.Failed) {
        // 下载失败 - 取消WebSocket订阅
        logger.error('下载失败:', wsMessage.data.Failed)
        isDownloading.value = false
        downloadFailed.value = true
        failureReason.value = wsMessage.data.Failed
        stopWebSocketHealthCheck()
        cancelWebSocketSubscription()
      }
    } else if (wsMessage.type === 'Info') {
      logger.debug('收到Info消息:', wsMessage.data)
      if (wsMessage.data.Error) {
        // 安装过程中的错误
        isInstalling.value = false
        message.error(`安装失败: ${wsMessage.data.Error}`)
      }
    }
  }
}

// 确保WebSocket订阅
const ensureWebSocketSubscription = () => {
  if (!updateSubscriptionId) {
    logger.info('创建WebSocket订阅')
    try {
      updateSubscriptionId = subscribe({ id: 'Update' }, handleUpdateMessage)
      logger.debug('WebSocket订阅ID:', updateSubscriptionId)

      // 添加测试消息处理函数来验证订阅是否工作
      logger.debug('订阅创建完成，等待WebSocket消息...')
    } catch (error) {
      logger.error('创建WebSocket订阅失败:', error)
    }
  } else {
    logger.debug('WebSocket订阅已存在:', updateSubscriptionId)
    // 验证订阅是否仍然有效
    logger.debug('验证现有订阅是否有效')
  }
}

// 取消WebSocket订阅
const cancelWebSocketSubscription = () => {
  if (updateSubscriptionId) {
    logger.info('取消WebSocket订阅:', updateSubscriptionId)
    try {
      unsubscribe(updateSubscriptionId)
    } catch (error) {
      logger.error('取消WebSocket订阅失败:', error)
    }
    updateSubscriptionId = ''
  }
}

// 启动WebSocket健康检查
const startWebSocketHealthCheck = () => {
  // 清除之前的检查
  stopWebSocketHealthCheck()

  logger.info('启动WebSocket健康检查')
  wsHealthCheckInterval = setInterval(() => {
    if (isDownloading.value) {
      logger.debug('WebSocket健康检查 - 订阅ID:', updateSubscriptionId)
      // 如果订阅丢失了，重新创建
      if (!updateSubscriptionId) {
        logger.warn('检测到WebSocket订阅丢失，重新创建')
        ensureWebSocketSubscription()
      }
    }
  }, 3000) // 每3秒检查一次
}

// 停止WebSocket健康检查
const stopWebSocketHealthCheck = () => {
  if (wsHealthCheckInterval) {
    logger.info('停止WebSocket健康检查')
    clearInterval(wsHealthCheckInterval)
    wsHealthCheckInterval = null
  }
}

// 监听 visible 变化
watch(
  () => props.visible,
  newVisible => {
    logger.debug('visible变化:', newVisible)
    logger.debug('当前props:', {
      visible: props.visible,
      latestVersion: props.latestVersion,
      updateData: props.updateData,
    })

    if (newVisible) {
      logger.info('窗口显示，确保WebSocket订阅并开始下载')
      // 确保WebSocket订阅处于活动状态
      ensureWebSocketSubscription()
      // 开始下载
      startDownload()
    } else {
      logger.info('窗口隐藏，重置状态但保持订阅')
      // 隐藏时重置状态，但不取消订阅（因为可能还在下载）
      resetState()
    }
  }
)

// 组件挂载时订阅 WebSocket 消息
onMounted(() => {
  logger.debug('组件挂载')
  ensureWebSocketSubscription()
})

// 组件卸载时取消订阅
onUnmounted(() => {
  logger.debug('组件卸载，清理资源')

  // 清理下载超时
  if (downloadTimeout) {
    clearTimeout(downloadTimeout)
    downloadTimeout = null
  }

  // 停止WebSocket健康检查
  stopWebSocketHealthCheck()

  // 清理WebSocket订阅
  cancelWebSocketSubscription()
})
</script>

<style scoped>
.update-download-modal :deep(.ant-modal-header) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 20px 24px 16px;
}

.update-download-modal :deep(.ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.update-download-modal :deep(.ant-modal-body) {
  padding: 16px 24px;
  background: var(--ant-color-bg-container);
}

.update-download-modal :deep(.ant-modal-content) {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 6px 30px rgba(0, 0, 0, 0.12);
}

.download-container {
  display: flex;
  flex-direction: column;
}

.download-progress-section {
  padding: 0;
}

.main-progress {
  padding: 12px 0;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.progress-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.download-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.progress-percent {
  font-size: 24px;
  font-weight: 700;
  color: var(--ant-color-primary);
  font-family:
    'SF Pro Display',
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    'Roboto',
    sans-serif;
}

.progress-bar {
  margin-bottom: 6px;
}

.progress-bar :deep(.ant-progress-bg) {
  border-radius: 4px;
  background: linear-gradient(90deg, var(--ant-color-primary), var(--ant-color-primary-active));
  box-shadow: 0 1px 4px rgba(22, 119, 255, 0.15);
}

.progress-bar :deep(.ant-progress-outer) {
  border-radius: 4px;
}

.progress-info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  line-height: 1.4;
  margin-top: 2px;
}

.left-info {
  display: flex;
  align-items: center;
  gap: 16px;
}

.file-progress {
  color: var(--ant-color-text);
  font-weight: 500;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

.download-speed {
  color: var(--ant-color-success);
  font-weight: 600;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  padding: 2px 8px;
  background: var(--ant-color-success-bg);
  border-radius: 4px;
  border: 1px solid var(--ant-color-success-border);
  font-size: 13px;
}

.right-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.eta-label {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.eta-value {
  color: var(--ant-color-warning);
  font-weight: 600;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  padding: 2px 8px;
  background: var(--ant-color-warning-bg);
  border-radius: 4px;
  border: 1px solid var(--ant-color-warning-border);
  font-size: 13px;
}

.animate-pulse {
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {

  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

.download-failed-section,
.download-success-section {
  text-align: center;
  padding: 20px 0;
}

.download-failed-section :deep(.ant-result-title) {
  color: var(--ant-color-error) !important;
  font-size: 20px;
  margin-bottom: 8px;
}

.download-success-section :deep(.ant-result-title) {
  color: var(--ant-color-success) !important;
  font-size: 20px;
  margin-bottom: 8px;
}

.failed-actions,
.success-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 24px;
}

.failed-actions .ant-btn,
.success-actions .ant-btn {
  min-width: 120px;
  height: 40px;
  border-radius: 8px;
  font-weight: 500;
}
</style>
