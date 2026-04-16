<template>
  <a-modal v-model:open="visible" :title="`涓嬭浇鏇存柊 ${latestVersion}`" :width="600" :footer="null" :mask-closable="false"
    :closable="false" :z-index="9999" class="update-download-modal" centered>
    <div class="download-container">
      <!-- 涓嬭浇杩涘害鍖哄煙 -->
      <div v-if="isDownloading" class="download-progress-section">
        <!-- 涓昏繘搴︽樉绀?-->
        <div class="main-progress">
          <div class="progress-header">
            <div class="progress-title">
              <a-spin :spinning="true" size="small" />
              <span class="download-title">涓嬭浇杩涘害</span>
            </div>
            <div class="progress-percent" :class="{
              'animate-pulse': downloadProgressPercent > 0 && downloadProgressPercent < 100,
            }">
              {{ downloadProgressPercent.toFixed(1) }}%
            </div>
          </div>

          <a-progress :percent="downloadProgressPercent" :show-info="false" stroke-color="var(--ant-color-primary)"
            trail-color="var(--ant-color-fill-secondary)" :stroke-width="8" class="progress-bar" />

          <!-- 杩涘害淇℃伅琛?-->
          <div class="progress-info-row">
            <div class="left-info">
              <span class="file-progress">{{ formatBytes(downloadProgress.downloaded_size) }} /
                {{ formatBytes(downloadProgress.file_size) }}</span>
              <span class="download-speed">{{ formatSpeed(downloadProgress.speed) }}</span>
            </div>
            <div v-if="estimatedTimeRemaining" class="right-info">
              <span class="eta-label">棰勮鍓╀綑鏃堕棿</span>
              <span class="eta-value">{{ estimatedTimeRemaining }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 涓嬭浇澶辫触鍖哄煙 -->
      <div v-if="downloadFailed" class="download-failed-section">
        <div class="failed-icon">
          <a-result status="error" title="涓嬭浇澶辫触" :sub-title="failureReason">
            <template #extra>
              <div class="failed-actions">
                <a-button type="primary" :loading="isRetrying" @click="handleRetry">
                  閲嶈瘯涓嬭浇
                </a-button>
                <a-button @click="handleCancel"> 鍙栨秷 </a-button>
              </div>
            </template>
          </a-result>
        </div>
      </div>

      <!-- 涓嬭浇鎴愬姛鍖哄煙 -->
      <div v-if="downloadCompleted" class="download-success-section">
        <a-result status="success" title="涓嬭浇瀹屾垚" sub-title="鏇存柊鍖呭凡涓嬭浇瀹屾垚锛屾槸鍚︾珛鍗冲畨瑁咃紵">
          <template #extra>
            <div class="success-actions">
              <a-button type="primary" :loading="isInstalling" @click="handleInstall">
                绔嬪嵆瀹夎
              </a-button>
              <a-button @click="handleLater"> 绋嶅悗瀹夎 </a-button>
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
import { updateApi } from '@/api'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
const logger = window.electronAPI.getLogger('鏇存柊涓嬭浇妯℃€佹')

// Props 瀹氫箟
interface Props {
  visible: boolean
  latestVersion: string
  updateData: Record<string, string[]>
}

const props = defineProps<Props>()

// Emits 瀹氫箟
const emit = defineEmits<{
  'update:visible': [value: boolean]
  completed: []
  cancelled: []
  installRequested: []
}>()

// WebSocket 鐩稿叧
let updateSubscriptionId: string = ''

// 鐘舵€佺鐞?
const isDownloading = ref(false)
const downloadFailed = ref(false)
const downloadCompleted = ref(false)
const isRetrying = ref(false)
const isInstalling = ref(false)
const failureReason = ref('')

// WebSocket鍋ュ悍妫€鏌?
let wsHealthCheckInterval: NodeJS.Timeout | null = null

// 涓嬭浇瓒呮椂瀹氭椂鍣?
let downloadTimeout: NodeJS.Timeout | null = null

// 涓嬭浇杩涘害鐩稿叧鐘舵€?
const downloadProgress = ref({
  downloaded_size: 0,
  file_size: 0,
  speed: 0,
})

// 璁＄畻涓嬭浇杩涘害鐧惧垎姣?
const downloadProgressPercent = computed(() => {
  const progress = downloadProgress.value
  if (!progress.file_size || progress.file_size <= 0) {
    return 0
  }
  const percent = (progress.downloaded_size / progress.file_size) * 100
  return Math.min(percent, 100)
})

// 璁＄畻鍓╀綑鏃堕棿
const estimatedTimeRemaining = computed(() => {
  const progress = downloadProgress.value
  const speed = progress.speed

  if (speed <= 0 || progress.downloaded_size <= 0 || progress.file_size <= 0) {
    return ''
  }

  const remainingBytes = progress.file_size - progress.downloaded_size
  const remainingSeconds = remainingBytes / speed

  if (remainingSeconds < 60) {
    return `${Math.ceil(remainingSeconds)}绉抈
  } else if (remainingSeconds < 3600) {
    const minutes = Math.floor(remainingSeconds / 60)
    const seconds = Math.ceil(remainingSeconds % 60)
    return `${minutes}鍒?{seconds}绉抈
  } else {
    const hours = Math.floor(remainingSeconds / 3600)
    const minutes = Math.floor((remainingSeconds % 3600) / 60)
    return `${hours}灏忔椂${minutes}鍒嗛挓`
  }
})

// 璁＄畻灞炴€?- 鍝嶅簲寮忓湴鎺ユ敹澶栭儴 visible 鐘舵€?
const visible = computed({
  get: () => props.visible,
  set: (value: boolean) => emit('update:visible', value),
})

// 鏍煎紡鍖栧瓧鑺傚ぇ灏?
const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 鏍煎紡鍖栭€熷害
const formatSpeed = (bytesPerSecond: number) => {
  if (bytesPerSecond === 0) return '0 B/s'

  const k = 1024
  const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s']
  const i = Math.floor(Math.log(bytesPerSecond) / Math.log(k))
  const value = bytesPerSecond / Math.pow(k, i)

  return parseFloat(value.toFixed(1)) + ' ' + sizes[i]
}

// 閲嶇疆鐘舵€?
const resetState = () => {
  // 娓呴櫎涓嬭浇瓒呮椂
  if (downloadTimeout) {
    clearTimeout(downloadTimeout)
    downloadTimeout = null
  }

  // 鍋滄WebSocket鍋ュ悍妫€鏌?
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

// 寮€濮嬩笅杞?
const startDownload = async () => {
  logger.info('寮€濮嬩笅杞芥祦绋?)

  // 纭繚WebSocket璁㈤槄宸插缓绔?
  ensureWebSocketSubscription()

  // 楠岃瘉WebSocket杩炴帴鐘舵€?
  logger.info('WebSocket杩炴帴鍑嗗灏辩华锛屽紑濮嬩笅杞?..')

  resetState()
  isDownloading.value = true

  try {
    // 纭繚鏈夌増鏈俊鎭紝濡傛灉娌℃湁鍒欏厛妫€鏌ユ洿鏂?
    if (!props.latestVersion) {
      logger.info('娌℃湁鐗堟湰淇℃伅锛屽厛妫€鏌ユ洿鏂?)
      const checkResult = await updateApi.check({
        current_version: (import.meta as any).env?.VITE_APP_VERSION || '1.0.0',
        if_force: false,
      })

      if (checkResult.code !== 200 || !checkResult.if_need_update) {
        downloadFailed.value = true
        isDownloading.value = false
        failureReason.value = '鏃犳硶鑾峰彇鏇存柊淇℃伅锛岃鍏堟鏌ユ洿鏂?
        return
      }
    }

    logger.info('璋冪敤涓嬭浇API')
    const res = await updateApi.download()
    logger.debug(`API鍝嶅簲: ${JSON.stringify(res)}`)

    if (res.code !== 200) {
      logger.error(`涓嬭浇璇锋眰澶辫触: ${res.message}`)
      downloadFailed.value = true
      isDownloading.value = false
      failureReason.value = res.message || '涓嬭浇璇锋眰澶辫触'
    } else {
      logger.info('涓嬭浇璇锋眰鎴愬姛锛岀瓑寰匴ebSocket杩涘害鏇存柊')

      // 鍚姩WebSocket鍋ュ悍妫€鏌?
      startWebSocketHealthCheck()

      // 璁剧疆涓嬭浇瓒呮椂锛?灏忔椂锛?
      downloadTimeout = setTimeout(
        () => {
          if (isDownloading.value) {
            logger.warn('涓嬭浇瓒呮椂锛屽彇娑圵ebSocket璁㈤槄')
            isDownloading.value = false
            downloadFailed.value = true
            failureReason.value = '涓嬭浇瓒呮椂锛岃妫€鏌ョ綉缁滆繛鎺ユ垨绋嶅悗閲嶈瘯'
            stopWebSocketHealthCheck()
            cancelWebSocketSubscription()
          }
        },
        2 * 60 * 60 * 1000
      )
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err)
    logger.error(`鍚姩涓嬭浇澶辫触: ${errorMsg}`)
    downloadFailed.value = true
    isDownloading.value = false
    failureReason.value = '缃戠粶璇锋眰澶辫触锛岃妫€鏌ョ綉缁滆繛鎺?
    stopWebSocketHealthCheck()
    cancelWebSocketSubscription()
  }
}

// 閲嶈瘯涓嬭浇
const handleRetry = async () => {
  isRetrying.value = true
  try {
    await startDownload()
  } finally {
    isRetrying.value = false
  }
}

// 鍙栨秷
const handleCancel = () => {
  visible.value = false
  emit('cancelled')
}

// 绋嶅悗瀹夎
const handleLater = () => {
  visible.value = false
  emit('completed')
}

// 绔嬪嵆瀹夎
const handleInstall = async () => {
  isInstalling.value = true
  try {
    const res = await updateApi.install()
    if (res.code === 200) {
      message.success('瀹夎绋嬪簭宸插惎鍔?)
      visible.value = false
      emit('installRequested')
    } else {
      message.error(res.message || '鍚姩瀹夎澶辫触')
    }
  } catch (err) {
    const errorMsg = err instanceof Error ? err.message : String(err)
    logger.error(`瀹夎澶辫触: ${errorMsg}`)
    message.error('鍚姩瀹夎澶辫触')
  } finally {
    isInstalling.value = false
  }
}

// WebSocket 娑堟伅澶勭悊
const handleUpdateMessage = (wsMessage: any) => {

  if (wsMessage.id === 'Update') {
    if (wsMessage.type === 'Update') {
      // 鏇存柊涓嬭浇杩涘害
      logger.debug(`鏇存柊涓嬭浇杩涘害: ${JSON.stringify(wsMessage.data)}`)
      const { downloaded_size, file_size, speed } = wsMessage.data

      // 浣跨敤Object.assign纭繚鍝嶅簲寮忔洿鏂?
      Object.assign(downloadProgress.value, {
        downloaded_size: downloaded_size || 0,
        file_size: file_size || 0,
        speed: speed || 0,
      })

      // 寮哄埗瑙﹀彂Vue鐨勫搷搴斿紡鏇存柊
      nextTick(() => {
        logger.debug(`杩涘害鏇存柊鍚庣姸鎬? ${JSON.stringify({
          杩涘害: downloadProgress.value,
          鐧惧垎姣? downloadProgressPercent.value.toFixed(2) + '%',
          姝ｅ湪涓嬭浇: isDownloading.value,
          璁㈤槄ID: updateSubscriptionId,
          鏃堕棿鎴? new Date().toISOString(),
        })}`)
      })
    } else if (wsMessage.type === 'Signal') {
      logger.debug(`鏀跺埌Signal娑堟伅: ${JSON.stringify(wsMessage.data)}`)

      // 娓呴櫎涓嬭浇瓒呮椂
      if (downloadTimeout) {
        clearTimeout(downloadTimeout)
        downloadTimeout = null
      }

      if (wsMessage.data.Accomplish) {
        // 涓嬭浇瀹屾垚 - 鍙栨秷WebSocket璁㈤槄
        logger.info('涓嬭浇瀹屾垚锛屽彇娑圵ebSocket璁㈤槄')
        isDownloading.value = false
        downloadCompleted.value = true
        stopWebSocketHealthCheck()
        cancelWebSocketSubscription()
      } else if (wsMessage.data.Failed) {
        // 涓嬭浇澶辫触 - 鍙栨秷WebSocket璁㈤槄
        logger.error(`涓嬭浇澶辫触: ${JSON.stringify(wsMessage.data.Failed)}`)
        isDownloading.value = false
        downloadFailed.value = true
        failureReason.value = wsMessage.data.Failed
        stopWebSocketHealthCheck()
        cancelWebSocketSubscription()
      }
    } else if (wsMessage.type === 'Info') {
      logger.debug(`鏀跺埌Info娑堟伅: ${JSON.stringify(wsMessage.data)}`)
      if (wsMessage.data.Error) {
        // 瀹夎杩囩▼涓殑閿欒
        isInstalling.value = false
        message.error(`瀹夎澶辫触: ${wsMessage.data.Error}`)
      }
    }
  }
}

// 纭繚WebSocket璁㈤槄
const ensureWebSocketSubscription = () => {
  if (!updateSubscriptionId) {
    logger.info('鍒涘缓WebSocket璁㈤槄')
    try {
      updateSubscriptionId = subscribe({ id: 'Update' }, handleUpdateMessage)
      logger.debug(`WebSocket璁㈤槄ID: ${updateSubscriptionId}`)

      // 娣诲姞娴嬭瘯娑堟伅澶勭悊鍑芥暟鏉ラ獙璇佽闃呮槸鍚﹀伐浣?
      logger.debug('璁㈤槄鍒涘缓瀹屾垚锛岀瓑寰匴ebSocket娑堟伅...')
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`鍒涘缓WebSocket璁㈤槄澶辫触: ${errorMsg}`)
    }
  } else {
    logger.debug(`WebSocket璁㈤槄宸插瓨鍦? ${updateSubscriptionId}`)
    // 楠岃瘉璁㈤槄鏄惁浠嶇劧鏈夋晥
    logger.debug('楠岃瘉鐜版湁璁㈤槄鏄惁鏈夋晥')
  }
}

// 鍙栨秷WebSocket璁㈤槄
const cancelWebSocketSubscription = () => {
  if (updateSubscriptionId) {
    logger.info(`鍙栨秷WebSocket璁㈤槄: ${updateSubscriptionId}`)
    try {
      unsubscribe(updateSubscriptionId)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`鍙栨秷WebSocket璁㈤槄澶辫触: ${errorMsg}`)
    }
    updateSubscriptionId = ''
  }
}

// 鍚姩WebSocket鍋ュ悍妫€鏌?
const startWebSocketHealthCheck = () => {
  // 娓呴櫎涔嬪墠鐨勬鏌?
  stopWebSocketHealthCheck()

  logger.info('鍚姩WebSocket鍋ュ悍妫€鏌?)
  wsHealthCheckInterval = setInterval(() => {
    if (isDownloading.value) {
      logger.debug(`WebSocket鍋ュ悍妫€鏌?- 璁㈤槄ID: ${updateSubscriptionId}`)
      // 濡傛灉璁㈤槄涓㈠け浜嗭紝閲嶆柊鍒涘缓
      if (!updateSubscriptionId) {
        logger.warn('妫€娴嬪埌WebSocket璁㈤槄涓㈠け锛岄噸鏂板垱寤?)
        ensureWebSocketSubscription()
      }
    }
  }, 3000) // 姣?绉掓鏌ヤ竴娆?
}

// 鍋滄WebSocket鍋ュ悍妫€鏌?
const stopWebSocketHealthCheck = () => {
  if (wsHealthCheckInterval) {
    logger.info('鍋滄WebSocket鍋ュ悍妫€鏌?)
    clearInterval(wsHealthCheckInterval)
    wsHealthCheckInterval = null
  }
}

// 鐩戝惉 visible 鍙樺寲
watch(
  () => props.visible,
  newVisible => {
    logger.debug(`visible鍙樺寲: ${newVisible}`)
    logger.debug(`褰撳墠props: ${JSON.stringify({
      visible: props.visible,
      latestVersion: props.latestVersion,
      updateData: props.updateData,
    })}`)

    if (newVisible) {
      logger.info('绐楀彛鏄剧ず锛岀‘淇漌ebSocket璁㈤槄骞跺紑濮嬩笅杞?)
      // 纭繚WebSocket璁㈤槄澶勪簬娲诲姩鐘舵€?
      ensureWebSocketSubscription()
      // 寮€濮嬩笅杞?
      startDownload()
    } else {
      logger.info('绐楀彛闅愯棌锛岄噸缃姸鎬佷絾淇濇寔璁㈤槄')
      // 闅愯棌鏃堕噸缃姸鎬侊紝浣嗕笉鍙栨秷璁㈤槄锛堝洜涓哄彲鑳借繕鍦ㄤ笅杞斤級
      resetState()
    }
  }
)

// 缁勪欢鎸傝浇鏃惰闃?WebSocket 娑堟伅
onMounted(() => {
  logger.debug('缁勪欢鎸傝浇')
  ensureWebSocketSubscription()
})

// 缁勪欢鍗歌浇鏃跺彇娑堣闃?
onUnmounted(() => {
  logger.debug('缁勪欢鍗歌浇锛屾竻鐞嗚祫婧?)

  // 娓呯悊涓嬭浇瓒呮椂
  if (downloadTimeout) {
    clearTimeout(downloadTimeout)
    downloadTimeout = null
  }

  // 鍋滄WebSocket鍋ュ悍妫€鏌?
  stopWebSocketHealthCheck()

  // 娓呯悊WebSocket璁㈤槄
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


