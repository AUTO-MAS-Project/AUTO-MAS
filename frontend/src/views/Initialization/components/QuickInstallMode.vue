<template>
  <div class="quick-install-mode">
    <div class="header">
      <a-typography-title :level="3">快速安装模式</a-typography-title>
      <p>正在从自建下载站获取预打包的环境和源码...</p>
    </div>

    <a-steps :current="displayCurrentStep" :status="stepStatus" class="install-steps">
      <a-step title="下载环境包" />
      <a-step title="解压环境" />
      <a-step title="下载源码" />
      <a-step title="解压源码" />
      <a-step title="更新代码" />
      <a-step title="安装依赖" />
      <a-step title="启动服务" />
    </a-steps>

    <div class="step-content">
      <!-- 当前步骤信息 -->
      <div class="current-step-info">
        <h4>{{ getCurrentStepTitle() }}</h4>
        <p>{{ currentStepDescription }}</p>
      </div>

      <!-- 进度条 -->
      <div class="progress-section">
        <a-progress 
          :percent="currentProgress" 
          :status="progressStatus"
          :show-info="true"
        />
        <div class="progress-text">{{ progressText }}</div>
        <div v-if="downloadSpeed" class="download-speed">{{ downloadSpeed }}</div>
        <div v-if="downloadInfo" class="download-info">
          {{ formatFileSize(downloadInfo.downloadedSize) }} / {{ formatFileSize(downloadInfo.totalSize) }}
        </div>
      </div>

      <!-- pip镜像源选择（在安装依赖步骤显示） -->
      <div v-if="currentStep === 5 && showPipMirrorSelection" class="pip-mirror-section">
        <h4>选择pip镜像源</h4>
        <div class="mirror-grid">
          <div
            v-for="mirror in pipMirrors"
            :key="mirror.key"
            class="mirror-card"
            :class="{ active: selectedPipMirror === mirror.key }"
            @click="selectedPipMirror = mirror.key"
          >
            <div class="mirror-header">
              <div class="mirror-title">
                <h5>{{ mirror.name }}</h5>
                <a-tag v-if="mirror.recommended" color="gold" size="small">推荐</a-tag>
              </div>
              <div class="speed-badge" :class="getSpeedClass(mirror.speed ?? null)">
                <span v-if="mirror.speed === null && !testingPipSpeed">未测试</span>
                <span v-else-if="testingPipSpeed">测试中...</span>
                <span v-else-if="mirror.speed === 9999">超时</span>
                <span v-else>{{ mirror.speed }}ms</span>
              </div>
            </div>
            <div class="mirror-description">{{ mirror.description }}</div>
          </div>
        </div>
        <div class="test-actions">
          <a-button :loading="testingPipSpeed" type="primary" @click="testPipMirrorSpeed">
            {{ testingPipSpeed ? '测速中...' : '重新测速' }}
          </a-button>
          <a-button type="default" @click="continueWithSelectedMirror">
            使用选中的镜像源继续
          </a-button>
        </div>
      </div>

      <!-- 详细信息 -->
      <div v-if="showDetails" class="details-section">
        <a-collapse v-model:activeKey="activeDetailsKey">
          <a-collapse-panel key="1" header="查看详细信息">
            <div class="detail-logs">
              <div v-for="(log, index) in detailLogs" :key="index" class="log-item">
                <span class="log-time">{{ log.time }}</span>
                <span class="log-message">{{ log.message }}</span>
              </div>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </div>

      <!-- 错误信息 -->
      <div v-if="errorMessage" class="error-section">
        <a-alert
          :message="errorMessage"
          type="error"
          show-icon
          closable
          @close="errorMessage = ''"
        />
      </div>
    </div>

    <div class="step-actions">
      <a-button
        type="default"
        size="large"
        @click="handleSwitchToManual"
      >
        切换到手动安装
      </a-button>

      <a-button
        v-if="currentStep === 5 && stepStatus === 'error'"
        type="primary"
        size="large"
        :loading="isProcessing"
        @click="retryCurrentStep"
      >
        重试启动服务
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { notification } from 'ant-design-vue'
import { saveConfig } from '@/utils/config.ts'
import { useUpdateChecker } from '@/composables/useUpdateChecker.ts'
import { connectAfterBackendStart } from '@/composables/useWebSocket.ts'

// Props
interface Props {
  onSwitchToManual: () => void
  onQuickComplete: () => void
}

const props = defineProps<Props>()

// 使用更新检查器
const { startPolling } = useUpdateChecker()

// 基础状态
const currentStep = ref(0)
const stepStatus = ref<'wait' | 'process' | 'finish' | 'error'>('process')
const isProcessing = ref(false)
const errorMessage = ref('')

// 进度状态
const currentProgress = ref(0)
const progressStatus = ref<'normal' | 'exception' | 'success'>('normal')
const progressText = ref('')
const currentStepDescription = ref('')
const downloadSpeed = ref('')
const downloadInfo = ref<{ downloadedSize: number; totalSize: number } | null>(null)

// pip镜像源相关
const showPipMirrorSelection = ref(false)
const selectedPipMirror = ref('tsinghua')
const testingPipSpeed = ref(false)
const pipMirrors = ref<Array<{ key: string; name: string; description: string; speed?: number | null; recommended?: boolean }>>([])

// 详细信息
const showDetails = ref(false)
const activeDetailsKey = ref<string[]>([])
const detailLogs = ref<Array<{ time: string; message: string }>>([])

// 显示的当前步骤
const displayCurrentStep = computed(() => currentStep.value)

// 步骤标题
const stepTitles = [
  '下载环境包',
  '解压环境包',
  '下载源码包',
  '解压源码包',
  '更新代码',
  '安装依赖',
  '启动服务'
]

function getCurrentStepTitle() {
  return stepTitles[currentStep.value] || '未知步骤'
}

// 添加日志
function addLog(message: string) {
  const now = new Date()
  const time = now.toLocaleTimeString()
  detailLogs.value.push({ time, message })
  
  // 限制日志数量
  if (detailLogs.value.length > 100) {
    detailLogs.value = detailLogs.value.slice(-100)
  }
}

// 更新进度
function updateProgress(progress: number, text: string, status: 'normal' | 'exception' | 'success' = 'normal') {
  currentProgress.value = progress
  progressText.value = text
  progressStatus.value = status
  addLog(text)
}

// 格式化文件大小
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

// 获取速度样式类
function getSpeedClass(speed: number | null) {
  if (speed === null) return 'speed-unknown'
  if (speed === 9999) return 'speed-timeout'
  if (speed < 500) return 'speed-fast'
  if (speed < 1500) return 'speed-medium'
  return 'speed-slow'
}

// 切换到手动安装
function handleSwitchToManual() {
  props.onSwitchToManual()
}

// 重试当前步骤
async function retryCurrentStep() {
  if (currentStep.value === 5) {
    await startBackendService()
  }
}

// 开始快速安装流程
async function startQuickInstall() {
  try {
    isProcessing.value = true
    stepStatus.value = 'process'
    showDetails.value = true

    // 步骤 0: 下载环境包
    currentStep.value = 0
    currentStepDescription.value = '正在从下载站获取预打包的Python和Git环境...'
    updateProgress(10, '开始下载环境包...')
    
    await downloadEnvironmentPackage()
    updateProgress(20, '环境包下载完成')

    // 步骤 1: 解压环境包
    currentStep.value = 1
    currentStepDescription.value = '正在解压环境包到本地目录...'
    updateProgress(30, '开始解压环境包...')
    
    await extractEnvironmentPackage()
    updateProgress(40, '环境包解压完成')

    // 步骤 2: 下载源码包
    currentStep.value = 2
    currentStepDescription.value = '正在从下载站获取最新的源码包...'
    updateProgress(50, '开始下载源码包...')
    
    await downloadSourcePackage()
    updateProgress(60, '源码包下载完成')

    // 步骤 3: 解压源码包
    currentStep.value = 3
    currentStepDescription.value = '正在解压源码包...'
    updateProgress(70, '开始解压源码包...')
    
    await extractSourcePackage()
    updateProgress(75, '源码包解压完成')

    // 步骤 4: 更新代码
    currentStep.value = 4
    currentStepDescription.value = '正在更新到最新代码...'
    updateProgress(80, '开始更新代码...')
    
    await updateSourceCode()
    updateProgress(85, '代码更新完成')

    // 步骤 5: 安装依赖
    currentStep.value = 5
    currentStepDescription.value = '正在准备安装Python依赖包...'
    updateProgress(87, '准备安装依赖...')
    
    // 显示pip镜像源选择
    console.log('开始显示pip镜像源选择...')
    await showPipMirrorSelectionStep()
    console.log('pip镜像源选择完成，依赖安装完成')

    // 步骤 6: 启动服务
    currentStep.value = 6
    currentStepDescription.value = '正在启动后端服务...'
    updateProgress(95, '开始启动服务...')
    console.log('开始启动后端服务...')
    
    await startBackendService()
    console.log('后端服务启动完成')
    updateProgress(100, '快速安装完成！', 'success')

    stepStatus.value = 'finish'
    
    // 延迟1秒后进入应用
    setTimeout(() => {
      props.onQuickComplete()
    }, 1000)

  } catch (error) {
    console.error('快速安装失败:', error)
    stepStatus.value = 'error'
    progressStatus.value = 'exception'
    errorMessage.value = error instanceof Error ? error.message : String(error)
    
    notification.error({
      message: '快速安装失败',
      description: errorMessage.value,
      duration: 0,
    })
  } finally {
    isProcessing.value = false
  }
}

// 下载环境包
async function downloadEnvironmentPackage() {
  const result = await window.electronAPI.downloadQuickEnvironment()
  if (!result.success) {
    throw new Error(`环境包下载失败: ${result.error}`)
  }
  
  // 更新配置状态
  await saveConfig({ 
    pythonInstalled: true,
    gitInstalled: true 
  })
}

// 解压环境包
async function extractEnvironmentPackage() {
  const result = await window.electronAPI.extractQuickEnvironment()
  if (!result.success) {
    throw new Error(`环境包解压失败: ${result.error}`)
  }
}

// 下载源码包
async function downloadSourcePackage() {
  const result = await window.electronAPI.downloadQuickSource()
  if (!result.success) {
    throw new Error(`源码包下载失败: ${result.error}`)
  }
}

// 解压源码包
async function extractSourcePackage() {
  const result = await window.electronAPI.extractQuickSource()
  if (!result.success) {
    throw new Error(`源码包解压失败: ${result.error}`)
  }
  
  // 更新配置状态
  await saveConfig({ backendExists: true })
}

// 更新源码
async function updateSourceCode() {
  const result = await window.electronAPI.updateQuickSource()
  // 更新失败不影响整体流程，只记录日志
  if (!result.success) {
    console.warn('代码更新失败，使用下载的版本继续:', result.error)
  }
}

// 显示pip镜像源选择步骤
async function showPipMirrorSelectionStep() {
  console.log('开始显示pip镜像源选择步骤...')
  
  // 加载pip镜像源
  await loadPipMirrors()
  console.log('pip镜像源加载完成')
  
  // 显示镜像源选择界面
  showPipMirrorSelection.value = true
  
  // 自动开始测速
  setTimeout(() => {
    testPipMirrorSpeed()
  }, 500)
  
  // 等待用户选择或自动继续
  return new Promise<void>((resolve, reject) => {
    console.log('设置quickInstallPipResolve回调函数...')
    // 设置一个全局的resolve函数，供用户点击按钮时调用
    ;(window as any).quickInstallPipResolve = async () => {
      console.log('quickInstallPipResolve被调用，开始安装依赖...')
      try {
        await proceedWithDependencyInstall()
        console.log('依赖安装完成，继续下一步...')
        resolve()
      } catch (error) {
        console.error('依赖安装失败:', error)
        reject(error)
      }
    }
    
    // 设置超时，防止无限等待
    setTimeout(() => {
      if (showPipMirrorSelection.value) {
        console.warn('pip镜像源选择超时，自动使用默认镜像源继续')
        ;(window as any).quickInstallPipResolve()
      }
    }, 30000) // 30秒超时
  })
}

// 用户点击继续按钮
function continueWithSelectedMirror() {
  console.log('用户点击继续按钮')
  if ((window as any).quickInstallPipResolve) {
    ;(window as any).quickInstallPipResolve()
  } else {
    console.error('quickInstallPipResolve函数不存在！')
  }
}

// 加载pip镜像源
async function loadPipMirrors() {
  // 从镜像管理器获取pip镜像源
  const { mirrorManager } = await import('@/utils/mirrorManager')
  pipMirrors.value = mirrorManager.getMirrors('pip')
  
  // 从配置中加载用户选择
  const { getConfig } = await import('@/utils/config')
  const config = await getConfig()
  selectedPipMirror.value = config.selectedPipMirror || 'tsinghua'
}

// 测试pip镜像源速度
async function testPipMirrorSpeed() {
  testingPipSpeed.value = true
  try {
    const promises = pipMirrors.value.map(async mirror => {
      mirror.speed = await testMirrorWithTimeout(mirror.url || `https://${mirror.key}.pypi.org/simple/`)
      return mirror
    })

    await Promise.all(promises)

    // 优先选择推荐的且速度最快的镜像源
    const sortedMirrors = [...pipMirrors.value].sort((a, b) => {
      if (a.recommended && !b.recommended) return -1
      if (!a.recommended && b.recommended) return 1
      return (a.speed || 9999) - (b.speed || 9999)
    })
    
    const fastest = sortedMirrors.find(m => m.speed !== 9999)
    if (fastest) {
      selectedPipMirror.value = fastest.key
    }
  } finally {
    testingPipSpeed.value = false
  }
}

// 测试镜像源延迟
async function testMirrorWithTimeout(url: string, timeout = 3000): Promise<number> {
  const startTime = Date.now()

  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    await fetch(url, {
      method: 'HEAD',
      mode: 'no-cors',
      signal: controller.signal,
    })

    clearTimeout(timeoutId)
    return Date.now() - startTime
  } catch (error) {
    return 9999 // 超时或失败
  }
}

// 继续安装依赖
async function proceedWithDependencyInstall() {
  console.log('开始执行依赖安装流程...')
  showPipMirrorSelection.value = false
  
  // 保存用户选择
  const { saveConfig } = await import('@/utils/config')
  await saveConfig({ selectedPipMirror: selectedPipMirror.value })
  
  updateProgress(91, '开始安装依赖...')
  console.log('开始调用installDependencies...')
  
  // 安装依赖
  const result = await window.electronAPI.installDependencies(selectedPipMirror.value)
  console.log('installDependencies调用完成，结果:', result)
  
  if (!result.success) {
    throw new Error(`依赖安装失败: ${result.error}`)
  }
  
  updateProgress(94, '依赖安装完成')
  console.log('依赖安装成功，更新配置状态...')
  
  // 更新配置状态
  await saveConfig({ dependenciesInstalled: true })
  console.log('依赖安装流程完成')
}

// 启动后端服务
async function startBackendService() {
  const result = await window.electronAPI.startBackend()
  if (!result.success) {
    throw new Error(`后端服务启动失败: ${result.error}`)
  }

  // 后端启动成功，建立WebSocket连接
  console.log('后端启动成功，正在建立WebSocket连接...')
  const wsConnected = await connectAfterBackendStart()
  if (!wsConnected) {
    console.warn('WebSocket连接建立失败，但继续进入应用')
  } else {
    console.log('WebSocket连接建立成功')
  }

  // WebSocket连接完成后，启动版本检查定时任务
  console.log('启动版本检查定时任务...')
  await startPolling()
}

// 监听下载进度
function handleDownloadProgress(progress: any) {
  if (progress.step !== undefined) {
    // 如果有步骤信息，更新当前步骤
    if (progress.step !== currentStep.value) {
      currentStep.value = progress.step
    }
  }
  
  // 更新下载速度和文件信息
  if (progress.speed) {
    downloadSpeed.value = progress.speed
  }
  
  if (progress.downloadedSize && progress.totalSize) {
    downloadInfo.value = {
      downloadedSize: progress.downloadedSize,
      totalSize: progress.totalSize
    }
  }
  
  updateProgress(progress.progress, progress.message, progress.status === 'error' ? 'exception' : 'normal')
}

// 组件挂载时开始安装
onMounted(() => {
  // 监听下载进度
  window.electronAPI.onDownloadProgress(handleDownloadProgress)
  
  // 开始快速安装
  startQuickInstall()
})

// 组件卸载时清理
onUnmounted(() => {
  // 清理全局变量
  if ((window as any).quickInstallPipResolve) {
    delete (window as any).quickInstallPipResolve
  }
  
  // 移除下载进度监听
  window.electronAPI.removeDownloadProgressListener()
})
</script>

<style scoped>
.quick-install-mode {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  max-width: 1000px;
  margin: 0 auto;
}

.header {
  text-align: center;
  margin-bottom: 20px;
}

.header h3 {
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 8px;
}

.header p {
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.install-steps {
  margin-bottom: 20px;
}

.step-content {
  background-color: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 24px;
  min-height: 300px;
}

.current-step-info {
  margin-bottom: 24px;
  text-align: center;
}

.current-step-info h4 {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 8px;
}

.current-step-info p {
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.progress-section {
  margin-bottom: 24px;
}

.progress-text {
  text-align: center;
  margin-top: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}

.download-speed {
  text-align: center;
  margin-top: 4px;
  color: var(--ant-color-primary);
  font-size: 16px;
  font-weight: 600;
}

.download-info {
  text-align: center;
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.details-section {
  margin-bottom: 24px;
}

.detail-logs {
  max-height: 200px;
  overflow-y: auto;
  background: var(--ant-color-bg-layout);
  border-radius: 4px;
  padding: 12px;
}

.log-item {
  display: flex;
  gap: 12px;
  margin-bottom: 4px;
  font-size: 12px;
  font-family: 'Courier New', monospace;
}

.log-time {
  color: var(--ant-color-text-tertiary);
  flex-shrink: 0;
}

.log-message {
  color: var(--ant-color-text-secondary);
}

.error-section {
  margin-bottom: 24px;
}

.step-actions {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 20px;
}

/* 响应式优化 */
@media (max-width: 768px) {
  .quick-install-mode {
    gap: 15px;
  }

  .header h3 {
    font-size: 20px;
  }

  .step-content {
    padding: 16px;
    min-height: 250px;
  }

  .step-actions {
    flex-direction: column;
    align-items: stretch;
  }
}

/* pip镜像源选择样式 */
.pip-mirror-section {
  margin-top: 24px;
  padding: 20px;
  background: var(--ant-color-bg-layout);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border);
}

.pip-mirror-section h4 {
  margin-bottom: 16px;
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
}

.mirror-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.mirror-card {
  padding: 12px;
  border: 2px solid var(--ant-color-border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--ant-color-bg-container);
}

.mirror-card:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.mirror-card.active {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.mirror-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.mirror-title {
  display: flex;
  align-items: center;
  gap: 6px;
}

.mirror-header h5 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.speed-badge {
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
}

.speed-badge.speed-unknown {
  color: var(--ant-color-text-tertiary);
}

.speed-badge.speed-fast {
  color: var(--ant-color-success);
}

.speed-badge.speed-medium {
  color: var(--ant-color-warning);
}

.speed-badge.speed-slow {
  color: var(--ant-color-error);
}

.speed-badge.speed-timeout {
  color: var(--ant-color-error);
}

.mirror-description {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  line-height: 1.4;
}

.test-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .mirror-grid {
    grid-template-columns: 1fr;
  }
  
  .test-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>