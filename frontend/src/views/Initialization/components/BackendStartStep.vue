<template>
  <div class="step-panel">
    <div class="install-section">
      <!-- 启动中 -->
      <div v-if="status === 'starting'" class="start-progress">
        <div class="status-text">{{ statusMessage }}</div>
        <a-progress :percent="progress" :status="progressStatus" />
      </div>

      <!-- 后端状态显示 -->
      <div v-else-if="status === 'running'" class="backend-status">
        <div class="status-grid" role="status" aria-label="后端服务状态">
          <div class="status-item">
            <span class="label">运行状态</span>
            <a-tag color="success">运行中</a-tag>
          </div>
          <div class="status-item">
            <span class="label">进程 PID</span>
            <span class="value">{{ backendPid || '-' }}</span>
          </div>
          <div class="status-item">
            <span class="label">WebSocket</span>
            <a-tag :color="wsConnected ? 'success' : 'warning'">
              {{ wsConnected ? '已连接' : '连接中…' }}
            </a-tag>
          </div>
          <div class="status-item">
            <span class="label">版本检查</span>
            <a-tag :color="pollingStarted ? 'success' : 'default'">
              {{ pollingStarted ? '已启动' : '准备中…' }}
            </a-tag>
          </div>
        </div>
      </div>

      <!-- 完成状态 -->
      <div v-else-if="status === 'success'" class="completed-status">
        <a-result
          status="success"
          title="后端启动成功"
          sub-title="应用已准备就绪，即将进入主界面"
        />
      </div>

      <!-- 失败状态 -->
      <div v-else-if="status === 'failed'" class="failed-status">
        <div class="failed-summary">
          <div class="failed-copy">
            <h4 class="failed-title">后端启动失败</h4>
            <p class="help-message">可先查看文档或截图下方完整日志寻求帮助。</p>
          </div>

          <a-space class="failed-actions">
            <a-button @click="handleOpenDocumentation">查看排障文档</a-button>
            <a-button v-if="showSkipButton" @click="emit('skip')">跳过此步骤</a-button>
            <a-button type="primary" @click="handleRetry">重试</a-button>
          </a-space>
        </div>

        <section v-if="backendLogs" class="failed-log-surface" aria-label="后端启动日志">
          <div class="failed-log-header">启动日志</div>
          <pre ref="backendLogRef" class="backend-log-output">{{ backendLogs }}</pre>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { connectAfterBackendStart } from '@/composables/useWebSocket'
import { useUpdateChecker } from '@/composables/useUpdateChecker'
const logger = window.electronAPI.getLogger('后端启动步骤')

// ==================== Props & Emits ====================
interface Props {
  showSkipButton?: boolean
}

withDefaults(defineProps<Props>(), {
  showSkipButton: false,
})

const emit = defineEmits<{
  'update:status': [status: 'waiting' | 'starting' | 'running' | 'success' | 'failed']
  complete: []
  error: [error: string]
  skip: []
}>()

// ==================== 状态管理 ====================
const status = ref<'waiting' | 'starting' | 'running' | 'success' | 'failed'>('waiting')
const statusMessage = ref('准备启动后端服务...')
const progress = ref(0)
const progressStatus = ref<'normal' | 'exception' | 'success'>('normal')
const errorMessage = ref('')
const backendLogs = ref('')

const backendPid = ref<number>()
const wsConnected = ref(false)
const pollingStarted = ref(false)
const backendLogRef = ref<HTMLElement | null>(null)

const backendStartFailureDocUrl =
  'https://doc.auto-mas.top/docs/FAQ.html#%E5%90%8E%E7%AB%AF%E5%90%AF%E5%8A%A8%E5%A4%B1%E8%B4%A5-%E8%B7%B3%E8%BF%87%E5%90%8E%E5%BA%94%E7%94%A8%E5%86%85%E4%B8%8D%E5%81%9C%E6%8A%A5%E9%94%99-network-error'

// 初始化更新检查器
const { startPolling } = useUpdateChecker()

// ==================== 方法 ====================

function scrollLogToBottom() {
  const logElement = backendLogRef.value
  if (!logElement) return

  logElement.scrollTop = logElement.scrollHeight
}

function queueScrollLogToBottom() {
  nextTick(() => {
    requestAnimationFrame(() => {
      scrollLogToBottom()
    })
  })
}

async function handleOpenDocumentation() {
  try {
    const result = await window.electronAPI.openUrl(backendStartFailureDocUrl)
    if (!result.success) {
      logger.error(`打开后端启动失败文档失败: ${String(result.error)}`)
      message.error(`无法打开文档，请手动访问：${backendStartFailureDocUrl}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`打开后端启动失败文档失败: ${errorMsg}`)
    message.error(`无法打开文档，请手动访问：${backendStartFailureDocUrl}`)
  }
}

/**
 * 启动后端服务
 */
async function startBackend() {
  status.value = 'starting'
  emit('update:status', 'starting')
  backendLogs.value = ''

  try {
    // 第一步：启动后端进程
    statusMessage.value = '正在启动后端进程...'
    progress.value = 10

    const result = await window.electronAPI.backendStart()

    if (!result.success) {
      backendLogs.value = result.logs || ''
      throw new Error(result.error || '后端启动失败')
    }

    // 获取后端状态
    const backendStatus = await window.electronAPI.backendStatus()
    backendPid.value = backendStatus.pid

    status.value = 'running'
    emit('update:status', 'running')
    progress.value = 30

    // 第二步：建立WebSocket连接
    statusMessage.value = '正在建立WebSocket连接...'
    progress.value = 40

    const connected = await connectAfterBackendStart()

    if (!connected) {
      logger.warn('WebSocket连接建立失败')
      wsConnected.value = false
      // WebSocket 连接失败不应该阻止继续，但需要警告
      // throw new Error('WebSocket连接建立失败，请检查后端服务')
    } else {
      wsConnected.value = true
    }

    progress.value = 60

    // 第三步：启动版本检查定时任务
    statusMessage.value = '正在启动版本检查任务...'
    progress.value = 70

    await startPolling()
    pollingStarted.value = true

    progress.value = 85

    // 第四步：等待后端完全就绪
    statusMessage.value = '等待后端服务完全就绪...'

    // 等待额外的时间确保后端完全启动
    await new Promise(resolve => setTimeout(resolve, 2000))

    progress.value = 95

    // 第五步：验证后端连接
    statusMessage.value = '验证后端连接...'

    try {
      // 尝试获取后端状态来验证连接
      const finalStatus = await window.electronAPI.backendStatus()
      if (!finalStatus.isRunning) {
        throw new Error('后端服务未在运行状态')
      }
    } catch (error) {
      const errMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`后端连接验证失败，但继续执行: ${errMsg}`)
    }

    progress.value = 100

    // 完成
    statusMessage.value = '后端服务已完全就绪'
    status.value = 'success'
    emit('update:status', 'success')
    progressStatus.value = 'success'

    // WebSocket 未连接时向用户披露，避免假成功
    if (!wsConnected.value) {
      message.warning('WebSocket 连接失败，部分功能可能不可用')
    }

    // 合并完成信息到一行日志
    logger.info(
      `后端服务启动完成 - PID: ${backendPid.value}, WebSocket: ${wsConnected.value ? '已连接' : '未连接'}, 版本检查: ${pollingStarted.value ? '已启动' : '未启动'}`
    )

    // 延迟1秒后通知完成，让用户看到成功状态
    setTimeout(() => {
      emit('complete')
    }, 1000)
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : String(error)
    logger.error(`后端启动失败: ${errMsg}`)

    status.value = 'failed'
    emit('update:status', 'failed')
    progressStatus.value = 'exception'
    errorMessage.value = errMsg
    emit('error', errMsg)
    queueScrollLogToBottom()
  }
}

/**
 * 重试启动
 */
async function handleRetry() {
  errorMessage.value = ''
  backendLogs.value = ''
  progress.value = 0
  progressStatus.value = 'normal'
  await startBackend()
}

// ==================== 生命周期 ====================
onMounted(() => {
  const api = window.electronAPI

  api.onBackendStatus?.((status: any) => {
    logger.debug(`收到后端状态: ${JSON.stringify(status)}`)
  })

  // 自动开始启动
  setTimeout(() => {
    startBackend()
  }, 500)
})

onUnmounted(() => {
  // 清理监听器
  const api = window.electronAPI
  api.removeBackendStatusListener?.()
})
</script>

<style scoped>
.step-panel {
  padding: var(--v6-space-5);
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

.step-panel * {
  box-sizing: border-box;
}

.install-section {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-5);
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
}

.start-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--v6-space-4);
  padding: var(--v6-space-10) 0;
}

.start-progress :deep(.ant-progress) {
  width: 98%;
  min-width: 200px;
}

.status-text {
  font-size: var(--v6-font-size-lg);
  color: var(--v6-color-text);
  text-align: center;
}

.backend-status {
  padding: var(--v6-space-3) 0;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--v6-space-3);
  width: 100%;
  box-sizing: border-box;
}

.status-item {
  display: flex;
  min-height: 56px;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: var(--v6-space-3) var(--v6-space-4);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-control);
  background: var(--v6-vibrancy-hover);
}

.status-item .label {
  font-weight: var(--v6-font-weight-medium);
  color: var(--v6-color-text-secondary);
}

.status-item .value {
  color: var(--v6-color-text);
  font-family: var(--v6-font-mono);
}

.completed-status {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.failed-status {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  padding-bottom: 4px;
}

.failed-summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v6-space-4);
  padding: var(--v6-space-4);
  border: 1px solid var(--v6-color-error-border);
  border-radius: var(--v6-radius-card);
  background: var(--v6-color-error-bg);
}

.failed-copy {
  min-width: 0;
}

.failed-eyebrow {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ant-color-error);
  letter-spacing: 0.02em;
}

.failed-title {
  margin: 0;
  font-size: var(--v6-font-size-xl);
  line-height: 1.2;
  color: var(--v6-color-text);
}

.help-message {
  margin: 10px 0 0;
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.failed-actions {
  flex-shrink: 0;
}

.failed-log-surface {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 0;
  flex: 1;
  overflow: hidden;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: var(--v6-color-surface);
}

.failed-log-header {
  flex: 0 0 auto;
  padding: var(--v6-space-3) var(--v6-space-4);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-semibold);
}

.backend-log-output {
  margin: 0;
  min-height: 280px;
  height: 100%;
  width: 100%;
  overflow: auto;
  padding: var(--v6-space-4);
  background: transparent;
  color: var(--v6-color-text);
  font-family: var(--v6-font-mono);
  font-size: var(--v6-font-size-sm);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  scrollbar-width: thin;
  scrollbar-color: var(--v6-color-border-strong) transparent;
}

.backend-log-output::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.backend-log-output::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 999px;
}

.backend-log-output::-webkit-scrollbar-thumb {
  border: 2px solid transparent;
  border-radius: 999px;
  background: var(--v6-color-border-strong);
  background-clip: padding-box;
}

.backend-log-output::-webkit-scrollbar-thumb:hover {
  background: var(--v6-color-text-tertiary);
  background-clip: padding-box;
}

@media (max-width: 768px) {
  .failed-summary {
    flex-direction: column;
  }

  .failed-actions {
    width: 100%;
  }

  .backend-log-output {
    min-height: 220px;
  }
}
</style>
