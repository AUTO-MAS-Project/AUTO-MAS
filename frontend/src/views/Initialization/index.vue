<template>
  <div class="initialization-page">
    <div class="header">
      <a-typography-title :level="3">
        欢迎使用 AUTO-MAS，正在自动配置您的运行环境
      </a-typography-title>
    </div>

    <a-steps :current="currentStepIndex" :status="stepStatus" class="init-steps">
      <a-step v-for="step in steps" :key="step.key" :title="step.title" />
    </a-steps>

    <div class="step-content">
      <!-- 当前步骤内容 -->
      <component 
        :is="currentStepComponent" 
        v-bind="currentStepProps"
        @update:selected-mirror="handleMirrorSelect"
        @retry="handleRetry"
        @skip="handleSkip"
        @complete="handleBackendComplete"
        @error="handleBackendError"
      />
    </div>

    <!-- 步骤操作按钮区域 - 后端启动完成后会自动进入应用，不需要手动按钮 -->
    <div class="step-actions"></div>
  </div>

  <!-- 跳过初始化弹窗 -->
  <a-modal
    v-model:open="forceEnterVisible"
    title="警告"
    ok-text="我知道我在做什么"
    cancel-text="取消"
    @ok="handleForceEnterConfirm"
  >
    <a-alert
      message="注意"
      description="你正在尝试跳过初始化流程，可能导致程序无法正常运行。请确保你已经手动完成了所有配置。"
      type="warning"
      show-icon
    />
  </a-modal>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { message } from 'ant-design-vue'
import { forceEnterApp } from '@/utils/appEntry.ts'
import { setInitialized } from '@/utils/config.ts'
import { mirrorManager } from '@/utils/mirrorManager.ts'
import StepPanel from './components/StepPanel.vue'
import BackendStartStep from './components/BackendStartStep.vue'
import type { MirrorConfig } from '@/types/mirror'

// ==================== 步骤定义 ====================
const steps = [
  { key: 'python', title: 'Python 安装', canSkip: false },
  { key: 'pip', title: 'Pip 安装', canSkip: false },
  { key: 'git', title: 'Git 安装', canSkip: false },
  { key: 'repository', title: '源码拉取', canSkip: true },
  { key: 'dependency', title: '依赖安装', canSkip: true },
  { key: 'backend', title: '后端启动', canSkip: true },
]

// ==================== 状态管理 ====================
const currentStepIndex = ref(0)
const stepStatus = ref<'wait' | 'process' | 'finish' | 'error'>('process')
const initCompleted = ref(false)
const forceEnterVisible = ref(false)
const isDev = import.meta.env.DEV
const appVersion = import.meta.env.VITE_APP_VERSION
const targetBranch = ref(isDev ? 'dev' : `release/${appVersion}`)

console.log(`当前环境: ${isDev ? '开发环境' : '生产环境'}, 目标分支: ${targetBranch.value}`)

// 各步骤状态
interface StepState {
  status: 'waiting' | 'processing' | 'success' | 'failed'
  message: string
  progress: number
  showMirrorSelection: boolean
  mirrors: MirrorConfig[]
  selectedMirror: string
  countdown: number
  currentMirror: string
  downloadSpeed: string
  downloadSize: string
  installMessage: string
  installProgress: number
  deployMessage: string
  deployProgress: number
  operationDesc: string
  checkInfo?: {
    exeExists?: boolean
    canRun?: boolean
    version?: string
    exists?: boolean
    isGitRepo?: boolean
    isHealthy?: boolean
    requirementsExists?: boolean
    needsInstall?: boolean
  }
  mirrorProgress?: {
    current: number
    total: number
  }
}

const stepStates = ref<Record<string, StepState>>({
  python: { status: 'waiting', message: '', progress: 0, showMirrorSelection: false, mirrors: [], selectedMirror: '', countdown: 0, currentMirror: '', downloadSpeed: '', downloadSize: '', installMessage: '', installProgress: 0, deployMessage: '', deployProgress: 0, operationDesc: '' },
  pip: { status: 'waiting', message: '', progress: 0, showMirrorSelection: false, mirrors: [], selectedMirror: '', countdown: 0, currentMirror: '', downloadSpeed: '', downloadSize: '', installMessage: '', installProgress: 0, deployMessage: '', deployProgress: 0, operationDesc: '' },
  git: { status: 'waiting', message: '', progress: 0, showMirrorSelection: false, mirrors: [], selectedMirror: '', countdown: 0, currentMirror: '', downloadSpeed: '', downloadSize: '', installMessage: '', installProgress: 0, deployMessage: '', deployProgress: 0, operationDesc: '' },
  repository: { status: 'waiting', message: '', progress: 0, showMirrorSelection: false, mirrors: [], selectedMirror: '', countdown: 0, currentMirror: '', downloadSpeed: '', downloadSize: '', installMessage: '', installProgress: 0, deployMessage: '', deployProgress: 0, operationDesc: '' },
  dependency: { status: 'waiting', message: '', progress: 0, showMirrorSelection: false, mirrors: [], selectedMirror: '', countdown: 0, currentMirror: '', downloadSpeed: '', downloadSize: '', installMessage: '', installProgress: 0, deployMessage: '', deployProgress: 0, operationDesc: '' },
  backend: { status: 'waiting', message: '', progress: 0, showMirrorSelection: false, mirrors: [], selectedMirror: '', countdown: 0, currentMirror: '', downloadSpeed: '', downloadSize: '', installMessage: '', installProgress: 0, deployMessage: '', deployProgress: 0, operationDesc: '' },
})

// 倒计时定时器
let countdownTimer: NodeJS.Timeout | null = null

// ==================== 计算属性 ====================
const currentStep = computed(() => steps[currentStepIndex.value])

const currentStepComponent = computed(() => {
  // 后端启动步骤使用专门的组件
  if (currentStep.value.key === 'backend') {
    return BackendStartStep
  }
  return StepPanel
})

const currentStepProps = computed(() => {
  const state = stepStates.value[currentStep.value.key]
  const step = currentStep.value
  
  // 对于环境安装步骤（Python/Pip/Git），失败时不显示镜像源选择
  const isEnvironmentStep = ['python', 'pip', 'git'].includes(step.key)
  
  return {
    title: step.title,
    status: state.status,
    message: state.message,
    progress: state.progress,
    showProgress: true,
    progressStatus: (state.status === 'failed' ? 'exception' : 'normal') as 'normal' | 'exception' | 'success',
    successTitle: `${step.title}完成`,
    showMirrorSelection: state.showMirrorSelection && !isEnvironmentStep, // 环境安装步骤失败时不显示镜像源选择
    showSkipButton: step.canSkip && state.status === 'failed', // 只有可跳过的步骤且失败时才显示跳过按钮
    mirrors: state.mirrors,
    selectedMirror: state.selectedMirror,
    countdown: state.countdown,
    currentMirror: state.currentMirror,
    downloadSpeed: state.downloadSpeed,
    downloadSize: state.downloadSize,
    installMessage: state.installMessage,
    installProgress: state.installProgress,
    deployMessage: state.deployMessage,
    deployProgress: state.deployProgress,
    operationDesc: state.operationDesc,
    checkInfo: state.checkInfo,
    mirrorProgress: state.mirrorProgress
  }
})

// ==================== 方法 ====================

// 格式化速度
function formatSpeed(bytesPerSecond: number): string {
  if (bytesPerSecond < 1024) {
    return `${Math.round(bytesPerSecond)} B/s`
  } else if (bytesPerSecond < 1024 * 1024) {
    const kb = bytesPerSecond / 1024
    return `${kb < 10 ? kb.toFixed(2) : kb.toFixed(1)} KB/s`
  } else {
    const mb = bytesPerSecond / 1024 / 1024
    return `${mb < 10 ? mb.toFixed(2) : mb.toFixed(1)} MB/s`
  }
}

// 格式化大小
function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${Math.round(bytes)} B`
  } else if (bytes < 1024 * 1024) {
    const kb = bytes / 1024
    return `${kb < 10 ? kb.toFixed(2) : kb.toFixed(1)} KB`
  } else if (bytes < 1024 * 1024 * 1024) {
    const mb = bytes / 1024 / 1024
    return `${mb < 10 ? mb.toFixed(2) : mb.toFixed(1)} MB`
  } else {
    const gb = bytes / 1024 / 1024 / 1024
    return `${gb < 10 ? gb.toFixed(2) : gb.toFixed(1)} GB`
  }
}

// 处理进度更新
function handleProgress(stepKey: string, progressData: any) {
  const state = stepStates.value[stepKey]
  if (!state) return

  const { stage, progress, message: msg, details } = progressData

  // 更新状态
  if (progress >= 100) {
    // 进度达到 100%，标记为成功
    state.status = 'success'
    state.message = msg || '完成'
    state.progress = 100
    state.currentMirror = ''
    state.downloadSpeed = ''
    state.downloadSize = ''
    state.installMessage = ''
    state.installProgress = 0
    state.deployMessage = ''
    state.deployProgress = 0
    state.operationDesc = ''
    console.log(`[${stepKey}] ✅ 完成 - 100%`)
  } else if (progress > 0) {
    // 进度更新中
    state.status = 'processing'
    state.message = msg
    // 控制进度条显示为整数
    state.progress = Math.round(progress)

    // 处理详细信息
    if (details) {
      if (details.checkInfo) {
        state.checkInfo = details.checkInfo
      }
      if (details.currentMirror) {
        state.currentMirror = details.currentMirror
      }
      if (details.mirrorProgress) {
        state.mirrorProgress = details.mirrorProgress
      }
      if (details.downloadSpeed) {
        state.downloadSpeed = formatSpeed(details.downloadSpeed)
      }
      if (details.downloadSize) {
        state.downloadSize = formatSize(details.downloadSize)
      }
      if (details.operationDesc) {
        state.operationDesc = details.operationDesc
      }
    }
    
    // 根据阶段更新安装信息
    if (stage === 'install') {
      state.installMessage = msg
      state.installProgress = Math.round(progress)
      state.deployMessage = ''
      state.deployProgress = 0
    } else if (stage === 'deploy') {
      // 部署阶段
      state.deployMessage = msg
      state.deployProgress = Math.round(progress)
      state.installMessage = ''
      state.installProgress = 0
    } else {
      // 其他阶段清空安装和部署信息
      state.installMessage = ''
      state.installProgress = 0
      state.deployMessage = ''
      state.deployProgress = 0
    }
    
    console.log(`[${stepKey}] ${msg} - ${Math.round(progress)}%`)
  } else if (progress === 0) {
    // 进度为 0，只在还没有进度时才重置
    // 避免在安装过程中因为某些中间步骤发送 progress: 0 导致进度条跳回0
    if (state.progress === 0 || state.status === 'waiting') {
      state.status = 'processing'
      state.message = msg || '准备中...'
      state.progress = 0
      console.log(`[${stepKey}] 开始 - ${msg}`)
    } else {
      // 如果已经有进度了，忽略 progress: 0 的更新，保持当前进度
      console.log(`[${stepKey}] 忽略 progress: 0 更新（当前进度: ${state.progress}%）`)
    }
  }
}

// 执行单个步骤
async function executeStep(stepKey: string): Promise<boolean> {
  const state = stepStates.value[stepKey]
  state.status = 'processing'
  state.progress = 0
  state.message = '正在执行...'

  try {
    let result: any

    switch (stepKey) {
      case 'python':
        result = await (window.electronAPI as any).installPython(state.selectedMirror)
        break
      case 'pip':
        result = await (window.electronAPI as any).installPip(state.selectedMirror)
        break
      case 'git':
        result = await (window.electronAPI as any).installGit(state.selectedMirror)
        break
      case 'repository':
        result = await (window.electronAPI as any).pullRepository(targetBranch.value, state.selectedMirror)
        break
      case 'dependency':
        result = await (window.electronAPI as any).installDependencies(state.selectedMirror)
        break
      case 'backend':
        // 后端启动由BackendStartStep组件处理
        // 该组件会触发 complete 事件，由 handleBackendComplete 处理
        // 这里直接返回 true，让循环结束
        // 但不触发自动进入应用，由 handleBackendComplete 控制
        return true
      default:
        throw new Error(`未知步骤: ${stepKey}`)
    }

    if (result.success) {
      // 确保进度更新到 100%
      state.status = 'success'
      state.progress = 100
      state.message = '阶段完成'
      state.currentMirror = ''
      state.downloadSpeed = ''
      state.downloadSize = ''
      state.installMessage = ''
      state.installProgress = 0
      state.operationDesc = ''
      
      console.log(`✅ 步骤 ${stepKey} 完成`)
      
      // 显示成功状态，让用户看到阶段完成
      await new Promise(resolve => setTimeout(resolve, 600))
      
      return true
    } else {
      throw new Error(result.error || '执行失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    console.error(`步骤 ${stepKey} 失败:`, errorMsg)
    
    state.status = 'failed'
    state.message = errorMsg
    state.showMirrorSelection = true
    
    // 开始倒计时
    startCountdown(stepKey)
    
    return false
  }
}

// 开始初始化流程
async function startInitialization() {
  console.log('开始初始化流程...')
  
  try {
    // 依次执行每个步骤
    for (let i = 0; i < steps.length; i++) {
      const step = steps[i]
      currentStepIndex.value = i
      
      console.log(`执行步骤 ${i + 1}/${steps.length}: ${step.title}`)
      
      const success = await executeStep(step.key)
      
      if (!success) {
        // 步骤失败，等待用户重试
        stepStatus.value = 'error'
        console.log(`步骤 ${step.title} 失败，等待用户重试`)
        return
      }
      
      console.log(`步骤 ${step.title} 完成`)
    }
    
    // 所有步骤完成
    // 注意：不在这里进入应用，由 handleBackendComplete 处理
    console.log('✅ 初始化流程执行完成，等待后端启动完成...')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    console.error('❌ 初始化失败:', errorMsg)
    stepStatus.value = 'error'
    message.error('初始化失败')
  }
}

function handleMirrorSelect(mirrorKey: string) {
  const state = stepStates.value[currentStep.value.key]
  if (state) {
    state.selectedMirror = mirrorKey
  }
}

async function handleSkip() {
  const stepKey = currentStep.value.key
  const state = stepStates.value[stepKey]
  
  console.log(`跳过步骤: ${stepKey}`)
  
  if (state) {
    // 清除倒计时
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
    
    // 标记为已跳过
    state.status = 'success'
    state.progress = 100
    state.message = '已跳过'
    state.showMirrorSelection = false
    state.countdown = 0
    
    message.warning(`已跳过 ${currentStep.value.title}`)
    
    // 等待一下让用户看到跳过状态
    await new Promise(resolve => setTimeout(resolve, 500))
    
    // 继续执行后续步骤
    for (let i = currentStepIndex.value + 1; i < steps.length; i++) {
      const step = steps[i]
      currentStepIndex.value = i
      
      console.log(`执行步骤 ${i + 1}/${steps.length}: ${step.title}`)
      
      const stepSuccess = await executeStep(step.key)
      
      if (!stepSuccess) {
        stepStatus.value = 'error'
        return
      }
    }
    
    // 所有步骤完成
    console.log('✅ 初始化流程执行完成，等待后端启动完成...')
  }
}

async function handleRetry() {
  const stepKey = currentStep.value.key
  const state = stepStates.value[stepKey]
  
  if (state) {
    // 清除倒计时
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
    
    // 重置状态
    state.showMirrorSelection = false
    state.countdown = 0
    
    console.log(`重试 ${stepKey}，使用镜像源: ${state.selectedMirror}`)
    
    // 重新执行当前步骤
    const success = await executeStep(stepKey)
    
    if (success) {
      // 继续执行后续步骤
      for (let i = currentStepIndex.value + 1; i < steps.length; i++) {
        const step = steps[i]
        currentStepIndex.value = i
        
        console.log(`执行步骤 ${i + 1}/${steps.length}: ${step.title}`)
        
        const stepSuccess = await executeStep(step.key)
        
        if (!stepSuccess) {
          stepStatus.value = 'error'
          return
        }
      }
      
      // 所有步骤完成
      console.log('✅ 初始化流程执行完成，等待后端启动完成...')
    }
  }
}

// 处理后端启动完成
async function handleBackendComplete() {
  console.log('后端启动完成，准备进入应用')
  const state = stepStates.value.backend
  state.status = 'success'
  state.progress = 100
  state.message = '后端服务启动成功'
  
  // 标记初始化完成
  initCompleted.value = true
  stepStatus.value = 'finish'
  message.success('初始化完成')
  
  console.log('等待后端服务完全稳定...')
  
  // 延迟进入应用，确保：
  // 1. 后端服务完全启动
  // 2. WebSocket 连接已建立
  // 3. 版本检查任务已启动
  // 4. 所有初始化工作已完成
  await new Promise(resolve => setTimeout(resolve, 2000))
  
  console.log('准备进入主应用界面')
  enterApp()
}

// 处理后端启动错误
function handleBackendError(error: string) {
  console.error('后端启动失败:', error)
  const state = stepStates.value.backend
  state.status = 'failed'
  state.message = error
  stepStatus.value = 'error'
}

function startCountdown(stepKey: string) {
  const state = stepStates.value[stepKey]
  if (!state) return
  
  state.countdown = 60
  
  countdownTimer = setInterval(() => {
    state.countdown--
    if (state.countdown <= 0) {
      if (countdownTimer) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
      // 自动重试
      handleRetry()
    }
  }, 1000)
}

async function handleForceEnterConfirm() {
  forceEnterVisible.value = false
  console.log('用户确认跳过初始化')
  await forceEnterApp('初始化-强行进入确认')
}

async function enterApp() {
  try {
    await setInitialized(true)
    console.log('设置初始化完成标记，准备进入应用...')
    await forceEnterApp('初始化完成后进入')
  } catch (error) {
    console.error('进入应用失败:', error)
    await forceEnterApp('初始化失败后强制进入')
  }
}

// ==================== 生命周期 ====================
// 从后端加载镜像源配置
async function loadMirrorConfigs() {
  const api = window.electronAPI as any
  
  try {
    console.log('正在从后端加载镜像源配置...')
    
    // 先初始化镜像服务
    await api.initMirrors()
    
    // 并行获取所有镜像源配置
    const [pythonMirrors, getPipMirrors, gitMirrors, repoMirrors, pipMirrors] = await Promise.all([
      api.getMirrors('python'),      // Python 安装包
      api.getMirrors('get_pip'),     // get-pip.py 脚本
      api.getMirrors('git'),         // Git 安装包
      api.getMirrors('repo'),        // Git 仓库
      api.getMirrors('pip_mirror'),  // PyPI 镜像源
    ])
    
    // 转换后端镜像源格式为前端格式
    const convertMirror = (mirror: any) => ({
      key: mirror.name,
      name: mirror.name,
      url: mirror.url,
      type: mirror.type,
      description: mirror.description,
      recommended: mirror.type === 'mirror',
    })
    
    // 设置各步骤的镜像源配置
    stepStates.value.python.mirrors = pythonMirrors.map(convertMirror)
    stepStates.value.pip.mirrors = getPipMirrors.map(convertMirror)
    stepStates.value.git.mirrors = gitMirrors.map(convertMirror)
    stepStates.value.repository.mirrors = repoMirrors.map(convertMirror)
    stepStates.value.dependency.mirrors = pipMirrors.map(convertMirror)
    
    console.log('✅ 镜像源配置加载完成')
    console.log('Python 镜像源:', stepStates.value.python.mirrors.map(m => m.name))
    console.log('Pip 镜像源:', stepStates.value.pip.mirrors.map(m => m.name))
    console.log('Git 镜像源:', stepStates.value.git.mirrors.map(m => m.name))
    console.log('Repository 镜像源:', stepStates.value.repository.mirrors.map(m => m.name))
    console.log('Dependency 镜像源:', stepStates.value.dependency.mirrors.map(m => m.name))
  } catch (error) {
    console.error('❌ 加载镜像源配置失败:', error)
    // 如果加载失败，使用本地兜底配置
    stepStates.value.python.mirrors = mirrorManager.getMirrors('python')
    stepStates.value.pip.mirrors = mirrorManager.getMirrors('get_pip')
    stepStates.value.git.mirrors = mirrorManager.getMirrors('git_package')
    stepStates.value.repository.mirrors = mirrorManager.getMirrors('git')
    stepStates.value.dependency.mirrors = mirrorManager.getMirrors('pip')
    console.log('⚠️ 使用本地兜底配置')
  }
}

onMounted(async () => {
  console.log('初始化界面已加载')
  
  const api = window.electronAPI as any
  
  // 加载镜像源配置
  await loadMirrorConfigs()
  
  // 监听各步骤进度
  api.onPythonProgress?.((progress: any) => handleProgress('python', progress))
  api.onPipProgress?.((progress: any) => handleProgress('pip', progress))
  api.onGitProgress?.((progress: any) => handleProgress('git', progress))
  api.onRepositoryProgress?.((progress: any) => handleProgress('repository', progress))
  api.onDependencyProgress?.((progress: any) => handleProgress('dependency', progress))
  
  // 监听后端日志和状态
  api.onBackendLog?.((log: string) => {
    console.log(`[Backend] ${log}`)
  })

  api.onBackendStatus?.((status: any) => {
    console.log(`[Backend] 状态更新: ${status.isRunning ? '运行中' : '已停止'}`)
    if (status.isRunning) {
      const state = stepStates.value.backend
      state.status = 'success'
      state.progress = 100
      state.message = `后端服务已启动，PID: ${status.pid}`
    }
  })
  
  // 延迟启动初始化
  setTimeout(() => {
    startInitialization()
  }, 500)
})

onUnmounted(() => {
  console.log('初始化界面卸载')
  
  // 清除倒计时
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
  
  const api = window.electronAPI as any
  
  // 移除监听器
  api.removePythonProgressListener?.()
  api.removePipProgressListener?.()
  api.removeGitProgressListener?.()
  api.removeRepositoryProgressListener?.()
  api.removeDependencyProgressListener?.()
  api.removeBackendLogListener?.()
  api.removeBackendStatusListener?.()
})
</script>

<style scoped>
.initialization-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  width: 100%;
  height: 100%;
  padding: 20px;
  box-sizing: border-box;
  background-color: var(--ant-color-bg-layout);
  color: var(--ant-color-text);
}

.header {
  text-align: center;
  margin-bottom: 20px;
  width: 100%;
  max-width: 1000px;
}

.header h3 {
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.init-steps {
  margin-bottom: 20px;
  width: 100%;
  max-width: 1000px;
}

.step-content {
  background-color: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 24px;
  /* min-height: 400px; Remove fixed min-height to allow shrinking on small screens */
  flex: 1; /* Take available vertical space */
  min-height: 0; /* Allow shrinking below content size */
  width: 100%;
  max-width: 1000px;
  box-sizing: border-box;
  display: flex; /* Enable flex for children (StepPanel) */
  flex-direction: column;
  overflow: hidden; /* Ensure content stays within border */
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 20px;
  width: 100%;
  max-width: 1000px;
}

/* 响应式优化 */
@media (max-width: 768px) {
  .initialization-page {
    gap: 15px;
    padding: 10px;
  }

  .header h3 {
    font-size: 20px;
  }

  .init-steps {
    :deep(.ant-steps-item-title) {
      white-space: normal;
    }
  }

  .step-content {
    padding: 16px;
    min-height: 300px;
  }
}

@media (max-width: 480px) {
  .step-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
