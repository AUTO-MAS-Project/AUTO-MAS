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
        <div v-if="backendPid" class="pid-info">
          PID: {{ backendPid }}
        </div>
      </div>

      <!-- 控制按钮 -->
      <div class="action-buttons">
        <button 
          @click="startBackend" 
          :disabled="isLoading || isBackendRunning"
          class="action-btn start-btn"
        >
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>▶️</span>
          启动后端
        </button>
        
        <button 
          @click="stopBackend" 
          :disabled="isLoading || !isBackendRunning"
          class="action-btn stop-btn"
        >
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>⏹️</span>
          停止后端
        </button>
        
        <button 
          @click="refreshStatus" 
          :disabled="isLoading"
          class="action-btn refresh-btn"
        >
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>🔄</span>
          刷新状态
        </button>
      </div>

      <!-- 操作结果显示 -->
      <div v-if="lastResult" class="result-card" :class="{ success: lastResult.success, error: !lastResult.success }">
        <div class="result-title">
          {{ lastResult.success ? '✅ 操作成功' : '❌ 操作失败' }}
        </div>
        <div v-if="lastResult.message" class="result-message">
          {{ lastResult.message }}
        </div>
        <div v-if="lastResult.error" class="result-error">
          错误: {{ lastResult.error }}
        </div>
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

      <button @click="getProcessInfo" :disabled="isLoading" class="action-btn info-btn">
        <span v-if="isLoading" class="loading-spinner">⏳</span>
        <span v-else>🔍</span>
        获取进程信息
      </button>
    </div>

    <!-- 快速操作 -->
    <div class="section">
      <h3 class="section-title">⚡ 快速操作</h3>
      
      <div class="quick-actions">
        <button @click="restartBackend" :disabled="isLoading" class="action-btn restart-btn">
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>🔄</span>
          重启后端
        </button>
        
        <button @click="forceKillProcesses" :disabled="isLoading" class="action-btn kill-btn">
          <span v-if="isLoading" class="loading-spinner">⏳</span>
          <span v-else>💀</span>
          强制结束所有进程
        </button>
      </div>
    </div>

    <!-- 日志区域 -->
    <div class="section">
      <h3 class="section-title">📝 操作日志</h3>
      
      <div class="log-container">
        <div v-if="logs.length === 0" class="no-logs">
          暂无日志记录
        </div>
        <div v-else class="log-entries">
          <div 
            v-for="(log, index) in logs" 
            :key="index" 
            class="log-entry" 
            :class="log.type"
          >
            <span class="log-time">{{ log.time }}</span>
            <span class="log-message">{{ log.message }}</span>
          </div>
        </div>
      </div>
      
      <button @click="clearLogs" class="action-btn clear-btn">
        🗑️ 清空日志
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

// 临时的类型断言，确保能访问到完整的electronAPI
const electronAPI = (window as any).electronAPI

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
      addLog('✅ 后端服务启动成功', 'success')
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
        addLog('✅ 后端服务已停止', 'success')
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
      addLog('✅ 所有相关进程已强制结束', 'success')
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

// 刷新状态
const refreshStatus = async () => {
  if (isLoading.value) return
  
  isLoading.value = true
  addLog('正在刷新后端状态...', 'info')
  
  try {
    // 获取相关进程信息
    const processes = await electronAPI.getRelatedProcesses()
    
    // 检查是否有Python进程在运行main.py
    const backendProcess = processes.find((proc: any) => 
      proc.command && proc.command.includes('main.py')
    )
    
    if (backendProcess) {
      isBackendRunning.value = true
      backendPid.value = backendProcess.pid
      addLog(`✅ 检测到后端进程 (PID: ${backendProcess.pid})`, 'success')
    } else {
      isBackendRunning.value = false
      backendPid.value = null
      addLog('ℹ️ 未检测到后端进程', 'info')
    }
    
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    addLog(`❌ 刷新状态失败: ${errorMsg}`, 'error')
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
    
    addLog('✅ 进程信息获取完成', 'success')
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
  
  // 初始化时获取状态
  refreshStatus()
  getProcessInfo()
  
  // 每5秒自动刷新状态
  statusInterval = setInterval(() => {
    refreshStatus()
  }, 5000)
})

onUnmounted(() => {
  if (statusInterval) {
    clearInterval(statusInterval)
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
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
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
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
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

.result-message, .result-error {
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
</style>
