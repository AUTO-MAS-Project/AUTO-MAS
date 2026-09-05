<template>
  <div class="backend-panel">
    <div
      v-if="status === 'starting' || status === 'running'"
      class="working-state"
      aria-live="polite"
    >
      <div class="working-symbol" aria-hidden="true">
        <LoadingOutlined spin />
      </div>
      <div class="state-copy">
        <h2>{{ t('init.backend.title') }}</h2>
        <p>{{ statusMessage }}</p>
      </div>

      <div class="stage-progress">
        <div class="progress-heading">
          <span>{{ t('init.page.stageProgress') }}</span>
          <strong>{{ t('init.page.progressPercent', { percent: backendProgress }) }}</strong>
        </div>
        <a-progress
          :percent="backendProgress"
          :show-info="false"
          :stroke-width="8"
          status="active"
        />
      </div>

      <div v-if="status === 'running'" class="service-state">
        <span>
          <span class="state-dot ready"></span>
          {{ t('init.backend.serviceReady') }}
        </span>
        <span>
          <span class="state-dot" :class="{ ready: wsConnected }"></span>
          {{ wsConnected ? t('init.backend.wsConnected') : t('init.backend.wsConnecting') }}
        </span>
        <span>
          <span class="state-dot" :class="{ ready: pollingStarted }"></span>
          {{ pollingStarted ? t('init.backend.versionReady') : t('init.backend.versionPreparing') }}
        </span>
      </div>

      <div class="elapsed-time">{{ t('init.page.elapsed', { time: elapsedText }) }}</div>
    </div>

    <div v-else-if="status === 'success'" class="completed-state" aria-live="polite">
      <CheckCircleFilled class="success-icon" aria-hidden="true" />
      <div class="state-copy">
        <h2>{{ t('init.backend.successTitle') }}</h2>
        <p>{{ t('init.backend.successSubtitle') }}</p>
      </div>
    </div>

    <div v-else-if="status === 'failed'" class="failed-state" aria-live="assertive">
      <a-alert
        type="error"
        :message="t('init.backend.failedTitle')"
        :description="errorMessage"
        show-icon
      />

      <p class="help-message">{{ t('init.backend.helpMessage') }}</p>

      <a-space class="failed-actions" size="middle" wrap>
        <a-button size="large" @click="handleOpenDocumentation">
          {{ t('init.backend.viewDocs') }}
        </a-button>
        <a-button v-if="showSkipButton" size="large" @click="emit('skip')">
          {{ t('init.step.skip') }}
        </a-button>
        <a-button type="primary" size="large" @click="handleRetry">
          {{ t('init.step.retry') }}
        </a-button>
      </a-space>

      <a-card
        v-if="backendLogs"
        size="small"
        :title="t('init.failure.logTitle')"
        class="failed-log-card"
      >
        <pre ref="backendLogRef" class="backend-log-output">{{ backendLogs }}</pre>
      </a-card>
    </div>

    <div v-else class="waiting-state">
      <ClockCircleOutlined class="waiting-icon" aria-hidden="true" />
      <h2>{{ t('init.backend.title') }}</h2>
      <p>{{ t('init.state.waiting') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckCircleFilled, ClockCircleOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import { bootstrapRealtimeResidents } from '@/bootstrap/realtimeResidents'
import { connectWithRetry, initializeAppLifecycle } from '@/composables/useAppLifecycle'
import { useUpdateChecker } from '@/composables/useUpdateChecker'

interface Props {
  showSkipButton?: boolean
  elapsedText?: string
}

withDefaults(defineProps<Props>(), {
  showSkipButton: false,
  elapsedText: '00:00',
})

const emit = defineEmits<{
  'update:status': [status: 'waiting' | 'starting' | 'running' | 'success' | 'failed']
  complete: []
  error: [error: string]
  skip: []
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('后端启动步骤')
const { startPolling } = useUpdateChecker()

const status = ref<'waiting' | 'starting' | 'running' | 'success' | 'failed'>('waiting')
const statusMessage = ref(t('init.backend.preparing'))
const errorMessage = ref('')
const backendLogs = ref('')
const backendPid = ref<number>()
const backendProgress = ref(0)
const wsConnected = ref(false)
const pollingStarted = ref(false)
const backendLogRef = ref<HTMLElement | null>(null)
let startTimer: ReturnType<typeof setTimeout> | null = null
let completeTimer: ReturnType<typeof setTimeout> | null = null

const backendStartFailureDocUrl =
  'https://doc.auto-mas.top/docs/FAQ.html#%E5%90%8E%E7%AB%AF%E5%90%AF%E5%8A%A8%E5%A4%B1%E8%B4%A5-%E8%B7%B3%E8%BF%87%E5%90%8E%E5%BA%94%E7%94%A8%E5%86%85%E4%B8%8D%E5%81%9C%E6%8A%A5%E9%94%99-network-error'

function queueScrollLogToBottom() {
  nextTick(() => {
    requestAnimationFrame(() => {
      const logElement = backendLogRef.value
      if (logElement) logElement.scrollTop = logElement.scrollHeight
    })
  })
}

async function handleOpenDocumentation() {
  try {
    const result = await window.electronAPI.openUrl(backendStartFailureDocUrl)
    if (!result.success) logger.error(`打开后端启动失败文档失败: ${String(result.error)}`)
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(`打开后端启动失败文档失败: ${errorMessage}`)
  }
}

async function startBackend() {
  status.value = 'starting'
  emit('update:status', 'starting')
  backendLogs.value = ''
  errorMessage.value = ''
  wsConnected.value = false
  pollingStarted.value = false
  backendProgress.value = 10

  try {
    statusMessage.value = t('init.backend.starting')
    const result = await window.electronAPI.backendStart()

    if (!result.success) {
      backendLogs.value = result.logs || ''
      throw new Error(result.error || t('init.backend.failedTitle'))
    }

    const backendStatus = await window.electronAPI.backendStatus()
    backendPid.value = backendStatus.pid
    backendProgress.value = 40
    status.value = 'running'
    emit('update:status', 'running')

    statusMessage.value = t('init.backend.connectingWs')
    bootstrapRealtimeResidents()
    initializeAppLifecycle()

    const connected = await connectWithRetry()
    wsConnected.value = connected
    backendProgress.value = 65
    if (!connected) logger.warn('WebSocket连接建立失败，将由应用内重连机制继续尝试')

    statusMessage.value = t('init.backend.startingVersionCheck')
    await startPolling()
    pollingStarted.value = true
    backendProgress.value = 85

    statusMessage.value = t('init.backend.verifying')
    try {
      const finalStatus = await window.electronAPI.backendStatus()
      if (!finalStatus.isRunning) throw new Error(t('init.backend.notRunning'))
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error)
      logger.warn(`后端连接验证失败，但继续执行: ${errorMessage}`)
    }

    backendProgress.value = 95
    statusMessage.value = t('init.backend.ready')
    status.value = 'success'
    backendProgress.value = 100
    emit('update:status', 'success')
    logger.info(
      `后端服务启动完成 - PID: ${backendPid.value}, WebSocket: ${wsConnected.value ? '已连接' : '未连接'}, 版本检查: ${pollingStarted.value ? '已启动' : '未启动'}`
    )

    completeTimer = setTimeout(() => emit('complete'), 300)
  } catch (error) {
    const errorMessageValue = error instanceof Error ? error.message : String(error)
    logger.error(`后端启动失败: ${errorMessageValue}`)
    status.value = 'failed'
    emit('update:status', 'failed')
    errorMessage.value = errorMessageValue
    emit('error', errorMessageValue)
    queueScrollLogToBottom()
  }
}

async function handleRetry() {
  await startBackend()
}

onMounted(() => {
  window.electronAPI.onBackendStatus?.(backendStatus => {
    logger.debug(`收到后端状态: ${JSON.stringify(backendStatus)}`)
  })

  startTimer = setTimeout(() => {
    void startBackend()
  }, 400)
})

onUnmounted(() => {
  if (startTimer) clearTimeout(startTimer)
  if (completeTimer) clearTimeout(completeTimer)
  window.electronAPI.removeBackendStatusListener?.()
})
</script>

<style scoped>
.backend-panel {
  min-height: 0;
  height: 100%;
}

.working-state,
.completed-state,
.waiting-state {
  display: flex;
  min-height: 360px;
  height: 100%;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  text-align: center;
}

.working-symbol {
  display: grid;
  place-items: center;
  width: 72px;
  height: 72px;
  margin-bottom: 24px;
  border: 1px solid var(--ant-color-primary-border);
  border-radius: 50%;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-size: 32px;
}

.state-copy,
.stage-progress {
  inline-size: min(100%, 72ch);
}

.stage-progress {
  margin-top: 24px;
  text-align: left;
}

.progress-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.progress-heading strong {
  color: var(--ant-color-primary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.state-copy h2,
.waiting-state h2 {
  margin: 0;
  color: var(--ant-color-text-heading);
  font-size: 24px;
  line-height: 1.35;
}

.state-copy p,
.waiting-state p {
  margin: 12px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 15px;
  line-height: 1.7;
}

.service-state {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  inline-size: min(100%, 72ch);
  gap: 10px 18px;
  margin-top: 24px;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.service-state > span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.state-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ant-color-text-quaternary);
}

.state-dot.ready {
  background: var(--ant-color-success);
}

.elapsed-time {
  margin-top: 16px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.success-icon {
  margin-bottom: 20px;
  color: var(--ant-color-success);
  font-size: 56px;
}

.failed-state {
  display: flex;
  min-height: 0;
  height: 100%;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  overflow-y: auto;
}

.help-message {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.failed-actions {
  align-self: flex-end;
}

.failed-log-card {
  display: flex;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

.failed-log-card :deep(.ant-card-body) {
  display: flex;
  min-height: 0;
  flex: 1;
  padding: 0;
}

.backend-log-output {
  min-height: 220px;
  max-height: 360px;
  width: 100%;
  margin: 0;
  padding: 14px 16px;
  overflow: auto;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.waiting-icon {
  margin-bottom: 20px;
  color: var(--ant-color-text-tertiary);
  font-size: 48px;
}

@media (max-width: 720px) {
  .working-state,
  .completed-state,
  .waiting-state {
    min-height: 300px;
    padding: 24px 16px;
  }

  .failed-state {
    padding: 16px;
  }

  .failed-actions {
    align-self: stretch;
  }
}
</style>
