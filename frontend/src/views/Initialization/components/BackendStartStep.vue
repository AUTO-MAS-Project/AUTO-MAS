<template>
  <div class="step-panel">
    <h3>启动应用</h3>
    
    <div class="install-section">
      <!-- 启动中 -->
      <div v-if="status === 'starting'" class="start-progress">
        <div class="status-text">{{ statusMessage }}</div>
        <a-progress :percent="progress" :status="progressStatus" />
      </div>

      <!-- 后端状态显示 -->
      <div v-else-if="status === 'running'" class="backend-status">
        <a-card title="后端服务状态" size="small">
          <div class="status-grid">
            <div class="status-item">
              <span class="label">运行状态:</span>
              <a-tag color="success">运行中</a-tag>
            </div>
            <div class="status-item">
              <span class="label">进程 PID:</span>
              <span class="value">{{ backendPid || '-' }}</span>
            </div>
            <div class="status-item">
              <span class="label">WebSocket:</span>
              <a-tag :color="wsConnected ? 'success' : 'warning'">
                {{ wsConnected ? '已连接' : '连接中...' }}
              </a-tag>
            </div>
            <div class="status-item">
              <span class="label">版本检查:</span>
              <a-tag :color="pollingStarted ? 'success' : 'default'">
                {{ pollingStarted ? '已启动' : '准备中...' }}
              </a-tag>
            </div>
          </div>
        </a-card>
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
        <a-result
          status="error"
          title="后端启动失败"
          :sub-title="errorMessage"
        >
          <template #extra>
            <a-space>
              <a-button v-if="showSkipButton" @click="emit('skip')">跳过此步骤</a-button>
              <a-button type="primary" @click="handleRetry">重试</a-button>
            </a-space>
          </template>
        </a-result>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { connectAfterBackendStart } from '@/composables/useWebSocket'
import { useUpdateChecker } from '@/composables/useUpdateChecker'
import { getLogger } from '@/utils/logger'

const logger = getLogger('后端启动步骤')

// ==================== Props & Emits ====================
interface Props {
  showSkipButton?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showSkipButton: false
})

const emit = defineEmits<{
  'update:status': [status: 'waiting' | 'starting' | 'running' | 'success' | 'failed']
  'complete': []
  'error': [error: string]
  'skip': []
}>()

// ==================== 状态管理 ====================
const status = ref<'waiting' | 'starting' | 'running' | 'success' | 'failed'>('waiting')
const statusMessage = ref('准备启动后端服务...')
const progress = ref(0)
const progressStatus = ref<'normal' | 'exception' | 'success'>('normal')
const errorMessage = ref('')

const backendPid = ref<number>()
const wsConnected = ref(false)
const pollingStarted = ref(false)

// 初始化更新检查器
const { startPolling } = useUpdateChecker()

// ==================== 方法 ====================

/**
 * 启动后端服务
 */
async function startBackend() {
  status.value = 'starting'
  emit('update:status', 'starting')
  
  try {
    // 第一步：启动后端进程
    statusMessage.value = '正在启动后端进程...'
    progress.value = 10
    
    const result = await (window.electronAPI as any).backendStart()
    
    if (!result.success) {
      throw new Error(result.error || '后端启动失败')
    }
    
    // 获取后端状态
    const backendStatus = await (window.electronAPI as any).backendStatus()
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
      const finalStatus = await (window.electronAPI as any).backendStatus()
      if (!finalStatus.isRunning) {
        throw new Error('后端服务未在运行状态')
      }
    } catch (error) {
      logger.warn('后端连接验证失败，但继续执行:', error)
    }
    
    progress.value = 100
    
    // 完成
    statusMessage.value = '后端服务已完全就绪'
    status.value = 'success'
    emit('update:status', 'success')
    progressStatus.value = 'success'
    
    // 合并完成信息到一行日志
    logger.info(`后端服务启动完成 - PID: ${backendPid.value}, WebSocket: ${wsConnected.value ? '已连接' : '未连接'}, 版本检查: ${pollingStarted.value ? '已启动' : '未启动'}`)
    
    // 延迟1秒后通知完成，让用户看到成功状态
    setTimeout(() => {
      emit('complete')
    }, 1000)
    
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : String(error)
    logger.error('后端启动失败:', errMsg)
    
    status.value = 'failed'
    emit('update:status', 'failed')
    progressStatus.value = 'exception'
    errorMessage.value = errMsg
    emit('error', errMsg)
  }
}

/**
 * 重试启动
 */
async function handleRetry() {
  errorMessage.value = ''
  progress.value = 0
  progressStatus.value = 'normal'
  await startBackend()
}

// ==================== 生命周期 ====================
onMounted(() => {
  const api = window.electronAPI as any
  
  api.onBackendStatus?.((status: any) => {
    logger.debug('后端启动步骤', `收到后端状态: ${JSON.stringify(status)}`)
  })
  
  // 自动开始启动
  setTimeout(() => {
    startBackend()
  }, 500)
})

onUnmounted(() => {
  // 清理监听器
  const api = window.electronAPI as any
  api.removeBackendStatusListener?.()
})
</script>

<style scoped>
.step-panel {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
}

.step-panel * {
  box-sizing: border-box;
}

.step-panel h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 20px;
}

.install-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
}

.start-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 40px 0;
}

.start-progress :deep(.ant-progress) {
  width: 98%;
  min-width: 200px;
}

.status-text {
  font-size: 16px;
  color: var(--ant-color-text);
  text-align: center;
}

.backend-status {
  padding: 12px 0;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  width: 100%;
  box-sizing: border-box;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-item .label {
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

.status-item .value {
  color: var(--ant-color-text);
}

.completed-status,
.failed-status {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}
</style>
