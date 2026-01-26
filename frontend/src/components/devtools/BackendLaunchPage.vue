<template>
  <div class="backend-launch-page">
    <div class="section">
      <h3 class="section-title">🚀 后端服务控制</h3>

      <!-- 后端状态显示 -->
      <div class="status-card" :class="{ running: isBackendRunning, stopped: !isBackendRunning }">
        <div class="status-indicator">
          <span class="status-dot" :class="{ active: isBackendRunning }"></span>
          <span class="status-text">
            {{ isBackendRunning ? '运行中' : '已停止' }}
          </span>
        </div>
        <div v-if="backendPid" class="pid-info">PID: {{ backendPid }}</div>
      </div>

      <!-- 控制按钮 -->
      <div class="action-buttons">
        <button :disabled="isLoading || isBackendRunning" class="action-btn start-btn" @click="startBackend">
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>▶️</span>
          启动后端
        </button>

        <button :disabled="isLoading || !isBackendRunning" class="action-btn stop-btn" @click="stopBackend">
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>⏹️</span>
          停止后端
        </button>

        <button :disabled="isLoading" class="action-btn refresh-btn" @click="refreshStatus">
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>🔄</span>
          刷新状态
        </button>
      </div>

      <!-- 操作结果显示 -->
      <div v-if="lastResult" class="result-card" :class="{ success: lastResult.success, error: !lastResult.success }">
        <div class="result-title">
          {{ lastResult.success ? '操作成功' : '❌ 操作失败' }}
        </div>
        <div v-if="lastResult.message" class="result-message">
          {{ lastResult.message }}
        </div>
        <div v-if="lastResult.error" class="result-error">错误: {{ lastResult.error }}</div>
      </div>
    </div>

    <!-- 进程信息 -->
    <div class="section">
      <h3 class="section-title">📊 进程信息</h3>

      <div class="process-info">
        <div class="info-row">
          <span class="info-label">Python路径:</span>
          <span class="info-value">{{ pythonPath || '未检测到' }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">主文件:</span>
          <span class="info-value">{{ mainPyPath || '未检测到' }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">工作目录:</span>
          <span class="info-value">{{ workingDir || '未知' }}</span>
        </div>
      </div>

      <button :disabled="isLoading" class="action-btn info-btn" @click="getProcessInfo">
        <span v-if="isLoading" class="loading-spinner">⏳</span>
        <span v-else>🔍</span>
        获取进程信息
      </button>
    </div>

    <!-- 快速操作 -->
    <div class="section">
      <h3 class="section-title">⚡ 快速操作</h3>

      <div class="quick-actions">
        <button :disabled="isLoading" class="action-btn restart-btn" @click="restartBackend">
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>🔄</span>
          重启后端
        </button>

        <button :disabled="isLoading" class="action-btn kill-btn" @click="forceKillProcesses">
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>💀</span>
          强制结束所有进程
        </button>
      </div>
    </div>

    <!-- WebSocket 调试区域 -->
    <div class="section">
      <h3 class="section-title">🔌 WebSocket 调试</h3>

      <!-- WebSocket状态 -->
      <div class="ws-status-card">
        <div class="status-row">
          <span class="status-label">WebSocket状态:</span>
          <span class="status-value" :class="wsStatus.toLowerCase().replace('已', '')">{{
            wsStatus
          }}</span>
        </div>
        <div class="status-row">
          <span class="status-label">后端状态:</span>
          <span class="status-value" :class="backendStatus">{{ backendStatus }}</span>
        </div>
        <div class="status-row">
          <span class="status-label">订阅数量:</span>
          <span class="status-value">{{ subscriberCount }}</span>
        </div>
        <div class="status-row">
          <span class="status-label">已连接过:</span>
          <span class="status-value">{{ connectionInfo.hasEverConnected ? '是' : '否' }}</span>
        </div>
      </div>

      <!-- 重连状态 -->
      <div class="ws-reconnect-card">
        <div class="status-row">
          <span class="status-label">重连次数:</span>
          <span class="status-value">{{ connectionInfo.wsReconnectAttempts || 0 }}</span>
        </div>
        <div class="status-row">
          <span class="status-label">自动重连中:</span>
          <span class="status-value" :class="{ active: connectionInfo.isAutoReconnecting }">
            {{ connectionInfo.isAutoReconnecting ? '是' : '否' }}
          </span>
        </div>
      </div>

      <!-- WebSocket控制按钮 -->
      <div class="ws-actions">
        <button :disabled="isWsReconnecting || connectionInfo.isAutoReconnecting" class="action-btn reconnect-btn"
          @click="handleManualReconnect">
          <span v-if="isWsReconnecting" class="loading-spinner">⏳</span>
          <span v-else>🔄</span>
          {{ isWsReconnecting ? '重连中...' : '手动重连' }}
        </button>

        <button :disabled="connectionInfo.isAutoReconnecting" class="action-btn reset-btn"
          @click="handleResetReconnect">
          🔧 重置重连状态
        </button>

        <button class="action-btn test-btn" @click="testWsMessage">💬 测试消息</button>
      </div>
    </div>

    <!-- 消息日志区域 -->
    <div class="section">
      <h3 class="section-title">📝 消息日志</h3>

      <div class="log-container">
        <div v-if="wsMessages.length === 0" class="no-logs">暂无WebSocket消息</div>
        <div v-else class="log-entries">
          <div v-for="(msg, index) in wsMessages" :key="index" class="log-entry ws-message">
            <span class="log-time">{{ msg.timestamp }}</span>
            <span class="log-message">{{ formatMessage(msg.data) }}</span>
          </div>
        </div>
      </div>

      <div class="log-actions">
        <button class="action-btn clear-btn" @click="clearWsMessages">🗑️ 清空消息</button>
        <button class="action-btn export-btn" @click="exportLogs">📤 导出日志</button>
      </div>
    </div>

    <!-- 操作日志区域 -->
    <div class="section">
      <h3 class="section-title">📝 操作日志</h3>

      <div class="log-container">
        <div v-if="logs.length === 0" class="no-logs">暂无日志记录</div>
        <div v-else class="log-entries">
          <div v-for="(log, index) in logs" :key="index" class="log-entry" :class="log.type">
            <span class="log-time">{{ log.time }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </div>

      <button class="action-btn clear-btn" @click="clearLogs">🗑️ 清空日志</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'

const logger = window.electronAPI.getLogger('后端调试面板')

// 临时的类型断言，确保能访问到完整的electronAPI
const electronAPI = (window as any).electronAPI

// WebSocket相关
const {
  subscribe,
  unsubscribe,
  sendRaw,
  getConnectionInfo,
  status,
  backendStatus,
  manualReconnect,
  resetReconnect,
  connectAfterBackendStart,
} = useWebSocket()

// 状态管理
const isBackendRunning = ref(false)
const isLoading = ref(false)
const backendPid = ref<number | null>(null)
const lastResult = ref<{ success: boolean; message?: string; error?: string } | null>(null)

// 进程信息
const pythonPath = ref<string>('')
const mainPyPath = ref<string>('')
const workingDir = ref<string>('')

// 日志管理
const logs = ref<Array<{ time: string; message: string; type: 'info' | 'success' | 'error' }>>([])

// WebSocket相关状态
const wsStatus = ref('')
const subscriberCount = ref(0)
const connectionInfo = ref<any>({})
const isWsReconnecting = ref(false)
const wsMessages = ref<Array<{ timestamp: string; data: any }>>([])
let wsSubscriptionId: string

// 添加日志
const addLog = (message: string, type: 'info' | 'success' | 'error' = 'info') => {
  const now = new Date()
  const time = now.toLocaleTimeString()
  logs.value.unshift({ time, message, type })

  // 限制日志数量
  if (logs.value.length > 50) {
    logs.value = logs.value.slice(0, 50)
  }
}

// 更新WebSocket状态
const updateWsStatus = () => {
  const connInfo = getConnectionInfo()
  wsStatus.value = status.value // 使用响应式的status
  subscriberCount.value = connInfo.subscriberCount
  connectionInfo.value = connInfo
}

// 处理WebSocket消息
const handleWsMessage = (message: WebSocketBaseMessage) => {

  // 添加到消息列表
  wsMessages.value.unshift({
    timestamp: new Date().toLocaleTimeString(),
    data: message,
  })

  // 保持最近20条消息
  if (wsMessages.value.length > 20) {
    wsMessages.value = wsMessages.value.slice(0, 20)
  }

  // 立即更新状态显示
  updateWsStatus()
  quickStatusCheck()
}

// 手动重连WebSocket
const handleManualReconnect = async () => {
  if (isWsReconnecting.value) return

  isWsReconnecting.value = true
  addLog('开始手动重连WebSocket...', 'info')

  try {
    const success = await manualReconnect()
    if (success) {
      addLog('WebSocket重连成功', 'success')
    } else {
      addLog('❌ WebSocket重连失败', 'error')
    }
  } catch (error) {
    addLog('❌ WebSocket重连异常', 'error')
  } finally {
    isWsReconnecting.value = false
    updateWsStatus()
  }
}

// 重置重连状态
const handleResetReconnect = () => {
  addLog('重置WebSocket重连状态', 'info')
  resetReconnect()
  updateWsStatus()
}

// 测试WebSocket消息
const testWsMessage = () => {
  const message = {
    id: 'debug_test_' + Date.now(),
    type: 'message',
    data: {
      type: 'Question',
      message_id: 'q_' + Date.now(),
      title: '调试测试问题',
      message: '这是来自后端调试面板的测试消息',
    },
  }

  logger.info('[后端调试] 发送测试消息:', message)
  sendRaw('message', message.data)
  addLog('发送测试消息: ' + message.data.title, 'info')
}

// 格式化消息显示
const formatMessage = (data: any) => {
  if (typeof data === 'object') {
    return (
      JSON.stringify(data, null, 0).substring(0, 100) +
      (JSON.stringify(data).length > 100 ? '...' : '')
    )
  }
  return String(data)
}

// 清空WebSocket消息
const clearWsMessages = () => {
  wsMessages.value = []
  addLog('WebSocket消息已清空', 'info')
}

// 导出日志
const exportLogs = () => {
  const allLogs = {
    wsMessages: wsMessages.value,
    operationLogs: logs.value,
    timestamp: new Date().toISOString(),
  }

  const blob = new Blob([JSON.stringify(allLogs, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `backend-debug-logs-${new Date().toISOString().split('T')[0]}.json`
  a.click()
  URL.revokeObjectURL(url)

  addLog('日志已导出', 'success')
}

// 快速状态检查 - 轻量级，主要基于WebSocket状态
const quickStatusCheck = () => {
  const wsConnected = status.value === '已连接'
  const wsConnecting = status.value === '连接中'
  const backendRunning = backendStatus.value === 'running'
  const currentBackendRunning = isBackendRunning.value

  // 基于WebSocket和backendStatus状态更新后端运行状态
  const shouldBeRunning = wsConnected || backendRunning

  if (shouldBeRunning && !currentBackendRunning) {
    isBackendRunning.value = true
    addLog(`检测到后端运行 (WS: ${status.value}, Backend: ${backendStatus.value})`, 'success')
  } else if (!shouldBeRunning && !wsConnecting && currentBackendRunning) {
    // 如果WebSocket断开且不是连接中状态，且backendStatus也不是running
    // 给一些时间缓冲，避免状态频繁切换
    setTimeout(() => {
      if (
        status.value !== '已连接' &&
        status.value !== '连接中' &&
        backendStatus.value !== 'running'
      ) {
        isBackendRunning.value = false
        backendPid.value = null
        addLog(`❌ 后端服务已停止 (WS: ${status.value}, Backend: ${backendStatus.value})`, 'error')
      }
    }, 1000) // 1秒缓冲时间，更快响应
  }
}

// 清空日志
const clearLogs = () => {
  logs.value = []
  addLog('日志已清空', 'info')
}

// 启动后端
const startBackend = async () => {
  if (isLoading.value) return

  isLoading.value = true
  lastResult.value = null
  addLog('正在启动后端服务...', 'info')

  try {
    const result = await electronAPI.startBackend()

    if (result.success) {
      lastResult.value = { success: true, message: '后端服务启动成功' }
      addLog('后端服务启动成功', 'success')

      // 等待后端完全启动
      addLog('⏳ 等待后端服务完全启动...', 'info')
      await new Promise(resolve => setTimeout(resolve, 2000))

      // 尝试连接WebSocket
      addLog('🔌 尝试连接WebSocket（最多3次重试）...', 'info')
      try {
        const connected = await connectAfterBackendStart()
        if (connected) {
          addLog('WebSocket连接成功，后端服务可用', 'success')
        } else {
          addLog('❌ WebSocket连接失败，请检查后端服务或手动重连', 'error')
        }
      } catch (error) {
        addLog(`❌ WebSocket连接异常: ${error}`, 'error')
      }

      await refreshStatus()
    } else {
      lastResult.value = { success: false, error: result.error }
      addLog(`❌ 后端服务启动失败: ${result.error}`, 'error')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    lastResult.value = { success: false, error: errorMsg }
    addLog(`❌ 启动后端时出现异常: ${errorMsg}`, 'error')
  } finally {
    isLoading.value = false
  }
}

// 停止后端
const stopBackend = async () => {
  if (isLoading.value) return

  isLoading.value = true
  lastResult.value = null
  addLog('正在停止后端服务...', 'info')

  try {
    // 检查stopBackend方法是否存在
    if (electronAPI.stopBackend) {
      const result = await electronAPI.stopBackend()

      if (result.success) {
        lastResult.value = { success: true, message: '后端服务已停止' }
        addLog('后端服务已停止', 'success')
        await refreshStatus()
      } else {
        lastResult.value = { success: false, error: result.error }
        addLog(`❌ 停止后端服务失败: ${result.error}`, 'error')
      }
    } else {
      // 如果没有stopBackend方法，使用强制结束进程的方式
      addLog('ℹ️ 使用强制结束进程的方式停止后端', 'info')
      await forceKillProcesses()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    lastResult.value = { success: false, error: errorMsg }
    addLog(`❌ 停止后端时出现异常: ${errorMsg}`, 'error')
  } finally {
    isLoading.value = false
  }
}

// 重启后端
const restartBackend = async () => {
  if (isLoading.value) return

  addLog('正在重启后端服务...', 'info')

  // 先停止
  if (isBackendRunning.value) {
    await stopBackend()
    // 等待一秒确保完全停止
    await new Promise(resolve => setTimeout(resolve, 1000))
  }

  // 再启动
  await startBackend()
}

// 强制结束所有相关进程
const forceKillProcesses = async () => {
  if (isLoading.value) return

  isLoading.value = true
  addLog('正在强制结束所有相关进程...', 'info')

  try {
    const result = await electronAPI.killAllProcesses()

    if (result.success) {
      lastResult.value = { success: true, message: '所有相关进程已强制结束' }
      addLog('所有相关进程已强制结束', 'success')
      await refreshStatus()
    } else {
      lastResult.value = { success: false, error: result.error }
      addLog(`❌ 强制结束进程失败: ${result.error}`, 'error')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    lastResult.value = { success: false, error: errorMsg }
    addLog(`❌ 强制结束进程时出现异常: ${errorMsg}`, 'error')
  } finally {
    isLoading.value = false
  }
}

// 刷新状态 - 基于WebSocket连接状态判断后端状态
const refreshStatus = async () => {
  if (isLoading.value) return

  isLoading.value = true
  addLog('正在刷新后端状态...', 'info')

  try {
    // 更新WebSocket状态
    updateWsStatus()

    // 主要基于WebSocket连接状态判断后端状态
    const wsConnected = status.value === '已连接'
    const backendRunning = backendStatus.value === 'running'

    // 如果WebSocket已连接，说明后端肯定在运行
    if (wsConnected) {
      isBackendRunning.value = true
      addLog(`WebSocket已连接，后端服务正在运行`, 'success')

      // 尝试获取进程ID
      try {
        const processes = await electronAPI.getRelatedProcesses()
        const backendProcess = processes.find(
          (proc: any) => proc.command && proc.command.includes('main.py')
        )
        if (backendProcess) {
          backendPid.value = backendProcess.pid
          addLog(`📋 后端进程PID: ${backendProcess.pid}`, 'info')
        } else {
          backendPid.value = null
          addLog(`⚠️ 无法获取后端进程PID，但WebSocket已连接`, 'info')
        }
      } catch (e) {
        // 获取PID失败不影响状态判断
        backendPid.value = null
        addLog(`⚠️ 获取进程信息失败，但WebSocket已连接`, 'info')
      }
    }
    // 如果WebSocket未连接，但后端状态显示运行中，可能是刚启动
    else if (backendRunning) {
      isBackendRunning.value = true
      addLog(`🔄 后端状态显示运行中，但WebSocket未连接`, 'info')
    }
    // WebSocket未连接且后端状态不是运行中
    else {
      isBackendRunning.value = false
      backendPid.value = null

      // 检查WebSocket状态给出更详细的信息
      if (status.value === '连接中') {
        addLog(`🔄 WebSocket连接中，后端可能正在启动`, 'info')
      } else if (status.value === '连接错误') {
        addLog(`❌ WebSocket连接错误，后端可能已停止`, 'error')
      } else {
        addLog(`ℹ️ WebSocket已断开，后端未运行`, 'info')
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    addLog(`❌ 刷新状态失败: ${errorMsg}`, 'error')
    // 发生错误时，基于WebSocket基本状态判断
    isBackendRunning.value = status.value === '已连接'
  } finally {
    isLoading.value = false
  }
}

// 获取进程信息
const getProcessInfo = async () => {
  if (isLoading.value) return

  isLoading.value = true
  addLog('正在获取进程信息...', 'info')

  try {
    // 这里可以调用一些API来获取Python路径等信息
    // 暂时使用模拟数据
    pythonPath.value = 'environment/python/python.exe'
    mainPyPath.value = 'main.py'
    workingDir.value = window.location.origin

    addLog('进程信息获取完成', 'success')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    addLog(`❌ 获取进程信息失败: ${errorMsg}`, 'error')
  } finally {
    isLoading.value = false
  }
}

// 定时刷新状态
let statusInterval: NodeJS.Timeout | null = null

onMounted(() => {
  addLog('📱 后端控制面板已加载', 'info')

  // 初始化时根据WebSocket状态设置后端状态
  const wsConnected = status.value === '已连接'
  const backendRunning = backendStatus.value === 'running'
  isBackendRunning.value = wsConnected || backendRunning

  if (isBackendRunning.value) {
    addLog(
      `初始化检测：后端服务正在运行 (WS: ${status.value}, Backend: ${backendStatus.value})`,
      'success'
    )
  } else {
    addLog(
      `❌ 初始化检测：后端服务未运行 (WS: ${status.value}, Backend: ${backendStatus.value})`,
      'info'
    )
  }

  // 获取其他信息
  refreshStatus()
  getProcessInfo()

  // 初始化WebSocket状态
  updateWsStatus()

  // 订阅WebSocket消息
  wsSubscriptionId = subscribe({}, handleWsMessage)
  addLog('🔌 WebSocket消息订阅已启动', 'info')

  // 每1秒自动刷新状态（更频繁，更及时）
  statusInterval = setInterval(() => {
    // 轻量级状态检查，主要基于WebSocket状态
    quickStatusCheck()
    updateWsStatus()
  }, 1000)
})

onUnmounted(() => {
  if (statusInterval) {
    clearInterval(statusInterval)
  }

  // 取消WebSocket订阅
  if (wsSubscriptionId) {
    unsubscribe(wsSubscriptionId)
    addLog('🔌 WebSocket消息订阅已取消', 'info')
  }
})
</script>

<style scoped>
.backend-launch-page {
  font-size: 11px;
  line-height: 1.4;
}

.section {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.section-title {
  margin: 0 0 8px 0;
  font-size: 12px;
  font-weight: bold;
  color: #4caf50;
}

/* 状态卡片 */
.status-card {
  padding: 8px;
  border-radius: 4px;
  margin-bottom: 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.status-card.running {
  background: rgba(76, 175, 80, 0.1);
  border-color: rgba(76, 175, 80, 0.3);
}

.status-card.stopped {
  background: rgba(244, 67, 54, 0.1);
  border-color: rgba(244, 67, 54, 0.3);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f44336;
  animation: pulse 2s infinite;
}

.status-dot.active {
  background: #4caf50;
}

@keyframes pulse {
  0% {
    opacity: 1;
  }

  50% {
    opacity: 0.5;
  }

  100% {
    opacity: 1;
  }
}

.status-text {
  font-weight: bold;
}

.pid-info {
  margin-top: 4px;
  font-size: 10px;
  color: #888;
}

/* 按钮样式 */
.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.action-btn {
  padding: 6px 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  cursor: pointer;
  font-size: 10px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 4px;
}

.action-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.2);
  transform: translateY(-1px);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.start-btn:hover:not(:disabled) {
  background: rgba(76, 175, 80, 0.3);
  border-color: rgba(76, 175, 80, 0.5);
}

.stop-btn:hover:not(:disabled) {
  background: rgba(244, 67, 54, 0.3);
  border-color: rgba(244, 67, 54, 0.5);
}

.restart-btn:hover:not(:disabled) {
  background: rgba(255, 193, 7, 0.3);
  border-color: rgba(255, 193, 7, 0.5);
}

.kill-btn:hover:not(:disabled) {
  background: rgba(156, 39, 176, 0.3);
  border-color: rgba(156, 39, 176, 0.5);
}

.loading-spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

/* 结果卡片 */
.result-card {
  padding: 8px;
  border-radius: 4px;
  margin-bottom: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.result-card.success {
  background: rgba(76, 175, 80, 0.1);
  border-color: rgba(76, 175, 80, 0.3);
}

.result-card.error {
  background: rgba(244, 67, 54, 0.1);
  border-color: rgba(244, 67, 54, 0.3);
}

.result-title {
  font-weight: bold;
  margin-bottom: 4px;
}

.result-message,
.result-error {
  font-size: 10px;
  line-height: 1.3;
}

.result-error {
  color: #ff6b6b;
}

/* 进程信息 */
.process-info {
  margin-bottom: 8px;
}

.info-row {
  display: flex;
  margin-bottom: 4px;
  font-size: 10px;
}

.info-label {
  width: 60px;
  color: #888;
  flex-shrink: 0;
}

.info-value {
  color: #fff;
  word-break: break-all;
}

/* 日志区域 */
.log-container {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  max-height: 120px;
  overflow-y: auto;
  margin-bottom: 8px;
}

.no-logs {
  padding: 8px;
  text-align: center;
  color: #888;
  font-size: 10px;
}

.log-entries {
  padding: 4px;
}

.log-entry {
  padding: 2px 4px;
  font-size: 9px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  display: flex;
  gap: 6px;
}

.log-entry:last-child {
  border-bottom: none;
}

.log-entry.success {
  color: #4caf50;
}

.log-entry.error {
  color: #f44336;
}

.log-entry.info {
  color: #888;
}

.log-time {
  color: #666;
  font-size: 8px;
  min-width: 60px;
}

.log-message {
  flex: 1;
  word-break: break-all;
}

.log-container::-webkit-scrollbar {
  width: 3px;
}

.log-container::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.05);
}

.log-container::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

/* WebSocket相关样式 */
.ws-status-card,
.ws-reconnect-card {
  padding: 6px 8px;
  border-radius: 4px;
  margin-bottom: 6px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.status-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2px;
  font-size: 10px;
}

.status-row:last-child {
  margin-bottom: 0;
}

.status-label {
  color: #999;
  font-weight: bold;
}

.status-value {
  color: #fff;
  font-weight: normal;
}

.status-value.connected {
  color: #4caf50;
}

.status-value.已连接 {
  color: #4caf50;
}

.status-value.连接 {
  color: #2196f3;
}

.status-value.断开 {
  color: #f44336;
}

.status-value.错误 {
  color: #ff5722;
}

.status-value.running {
  color: #4caf50;
}

.status-value.stopped,
.status-value.error {
  color: #f44336;
}

.status-value.active {
  color: #4caf50;
  font-weight: bold;
}

.ws-actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.reconnect-btn {
  background: #4caf50 !important;
}

.reconnect-btn:hover:not(:disabled) {
  background: #45a049 !important;
}

.reset-btn {
  background: #ff5722 !important;
}

.reset-btn:hover:not(:disabled) {
  background: #e64a19 !important;
}

.test-btn {
  background: #2196f3 !important;
}

.test-btn:hover:not(:disabled) {
  background: #1976d2 !important;
}

.log-entry.ws-message {
  border-left: 3px solid #2196f3;
  background: rgba(33, 150, 243, 0.05);
}

.log-actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
}

.export-btn {
  background: #9c27b0 !important;
}

.export-btn:hover:not(:disabled) {
  background: #7b1fa2 !important;
}
</style>
