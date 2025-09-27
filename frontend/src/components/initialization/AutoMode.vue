<template>
  <div class="auto-mode">
    <div class="header">
      <img src="/src/assets/AUTO-MAS.ico" alt="logo" class="logo" />
      <a-typography-title :level="1">AUTO-MAS</a-typography-title>
    </div>
    <div class="tip">
      <a-typography-title :level="3">检测到环境已配置，正在启动后端~~</a-typography-title>
    </div>

    <div class="auto-progress">
      <a-spin size="large" />
      <div class="progress-text">{{ progressText }}</div>
      <a-progress :percent="progress" :status="progressStatus" />

      <!-- 重试倒计时显示 -->
      <div v-if="showRetryCountdown" class="retry-countdown">
        <a-alert
          type="warning"
          show-icon
          :message="`更新失败，${retryCountdown} 秒后重试 (第 ${currentRetryCount}/${maxRetries} 次)`"
        />
        <div class="retry-actions">
          <a-button
            @click="retryNow"
            type="primary"
            size="small"
          >
            立即重试
          </a-button>
        </div>
      </div>
    </div>

    <div class="auto-actions">
      <a-button 
        @click="handleSwitchToManual" 
        type="primary" 
        size="large"
      >
        重新配置环境
      </a-button>
      <a-button 
        @click="handleForceEnter" 
        type="default" 
        size="large"
      >
        强行进入应用
      </a-button>
    </div>
  </div>

  <!-- 强行进入应用弹窗 -->
  <a-modal
    v-model:open="forceEnterVisible"
    title="警告"
    ok-text="我知道我在做什么"
    cancel-text="取消"
    @ok="handleForceEnterConfirm"
  >
    <a-alert
      message="注意"
      description="你正在尝试跳过后端启动流程，可能导致程序无法正常运行。请确保你已经手动完成了所有配置并且后端已成功启动。"
      type="warning"
      show-icon
    />
  </a-modal>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { getConfig } from '@/utils/config'
import { mirrorManager } from '@/utils/mirrorManager'
import router from '@/router'
import { useUpdateChecker } from '@/composables/useUpdateChecker'
import { connectAfterBackendStart } from '@/composables/useWebSocket'
import { message } from 'ant-design-vue'

// Props
interface Props {
  onSwitchToManual: () => void
  onAutoComplete: () => void
}

const props = defineProps<Props>()

// 使用更新检查器
const { startPolling } = useUpdateChecker()

// 状态
const progress = ref(0)
const progressText = ref('')
const progressStatus = ref<'normal' | 'exception' | 'success'>('normal')

// 状态：控制是否取消自动启动
const aborted = ref(false)

// 状态：控制弹窗显隐
const forceEnterVisible = ref(false)

// 重试相关状态
const showRetryCountdown = ref(false)
const retryCountdown = ref(5) // 修改为5秒
const currentRetryCount = ref(0)
const maxRetries = ref(999) // 设置为999，表示几乎无限重试
const retryTimer = ref<NodeJS.Timeout | null>(null)
const countdownTimer = ref<NodeJS.Timeout | null>(null)

// 清理定时器
function clearTimers() {
  if (retryTimer.value) {
    clearTimeout(retryTimer.value)
    retryTimer.value = null
  }
  if (countdownTimer.value) {
    clearInterval(countdownTimer.value)
    countdownTimer.value = null
  }
}

// 开始重试倒计时
function startRetryCountdown() {
  showRetryCountdown.value = true
  retryCountdown.value = 5 // 修改为5秒
  progressStatus.value = 'exception'

  // 倒计时定时器
  countdownTimer.value = setInterval(() => {
    retryCountdown.value--
    if (retryCountdown.value <= 0) {
      clearTimers()
      showRetryCountdown.value = false
      retryNow()
    }
  }, 1000)
}

// 立即重试
function retryNow() {
  clearTimers()
  showRetryCountdown.value = false
  progressStatus.value = 'normal'

  // 重新开始自动流程
  console.log(`开始第 ${currentRetryCount.value + 1} 次重试`)
  startAutoProcess()
}

// 点击"强行进入应用"按钮，显示弹窗
function handleForceEnter() {
  clearTimers()
  showRetryCountdown.value = false
  forceEnterVisible.value = true
}

// 确认弹窗中的"我知道我在做什么"按钮，直接进入应用
function handleForceEnterConfirm() {
  clearTimers()
  aborted.value = true
  forceEnterVisible.value = false
  router.push('/home')
}

// 事件处理 - 增强重新配置环境按钮功能
function handleSwitchToManual() {
  clearTimers() // 清理所有定时器
  showRetryCountdown.value = false // 隐藏重试倒计时
  aborted.value = true // 设置中断标志
  currentRetryCount.value = 0 // 重置重试计数
  progressStatus.value = 'normal' // 重置进度状态
  props.onSwitchToManual()
}

// 自动启动流程
async function startAutoProcess() {
  try {
    // 重置中断状态
    if (currentRetryCount.value === 0) {
      aborted.value = false
    }

    // 获取配置中保存的镜像源设置
    const config = await getConfig()
    if (aborted.value) return

    progressText.value = '检查Git仓库更新...'
    progress.value = 20

    // 检查Git仓库是否有更新
    const hasUpdate = await checkGitUpdate()
    if (aborted.value) return

    if (hasUpdate) {
      progressText.value = '发现更新，正在更新代码...'
      progress.value = 40

      // 尝试更新代码，支持镜像源重试
      const updateSuccess = await tryUpdateBackendWithRetry(config)
      if (aborted.value) return

      if (!updateSuccess) {
        // 代码更新失败，开始重试流程
        currentRetryCount.value++

        if (currentRetryCount.value < maxRetries.value) {
          progressText.value = `代码更新失败，准备重试...`
          console.log(`代码更新失败，准备进行第 ${currentRetryCount.value} 次重试`)
          startRetryCountdown()
          return
        } else {
          // 达到最大重试次数
          progressText.value = '代码更新失败，已达到最大重试次数'
          progressStatus.value = 'exception'
          return
        }
      }

      // 代码更新成功后，检查并安装依赖
      progressText.value = '检查并安装依赖包...'
      progress.value = 60

      // 尝试安装依赖，支持镜像源重试
      const dependenciesSuccess = await tryInstallDependenciesWithRetry(config)
      if (aborted.value) return

      if (!dependenciesSuccess) {
        // 依赖安装失败，开始重试流程
        currentRetryCount.value++

        if (currentRetryCount.value < maxRetries.value) {
          progressText.value = `依赖安装失败，准备重试...`
          console.log(`依赖安装失败，准备进行第 ${currentRetryCount.value} 次重试`)
          startRetryCountdown()
          return
        } else {
          // 达到最大重试次数
          progressText.value = '依赖安装失败，已达到最大重试次数'
          progressStatus.value = 'exception'
          return
        }
      }
    } else {
      // 没有更新，跳过依赖安装，直接设置进度
      console.log('代码没有更新，跳过依赖安装阶段')
      progressText.value = '代码无需更新，跳过依赖安装...'
      progress.value = 60
      // 短暂延迟以显示跳过信息
      await new Promise(resolve => setTimeout(resolve, 1000))
    }

    progressText.value = '启动后端服务...'
    progress.value = 80
    await startBackendService()
    if (aborted.value) return

    progressText.value = '启动完成！'
    progress.value = 100
    progressStatus.value = 'success'

    // 重置重试计数器
    currentRetryCount.value = 0

    console.log('自动启动流程完成，即将进入应用')

    // 延迟0.5秒后自动进入应用
    setTimeout(() => {
      props.onAutoComplete()
    }, 500)

  } catch (error) {
    console.error('自动启动流程失败', error)

    // 如果是后端启动失败，也要重试
    currentRetryCount.value++

    if (currentRetryCount.value < maxRetries.value) {
      progressText.value = `启动失败: ${error instanceof Error ? error.message : String(error)}，准备重试...`
      console.log(`后端启动失败，准备进行第 ${currentRetryCount.value} 次重试`)
      startRetryCountdown()
    } else {
      progressText.value = `自动启动失败: ${error instanceof Error ? error.message : String(error)}`
      progressStatus.value = 'exception'
    }
  }
}

// 检查Git更新
async function checkGitUpdate(): Promise<boolean> {
  try {
    // 调用Electron API检查Git仓库是否有更新
    const result = await window.electronAPI.checkGitUpdate()
    return result.hasUpdate || false
  } catch (error) {
    console.warn('检查Git更新失败:', error)
    // 如果检查失败，假设有更新，这样会触发代码拉取和依赖安装
    return true
  }
}

// 尝试更新后端代码，支持镜像源重试
async function tryUpdateBackendWithRetry(config: any): Promise<boolean> {
  // 获取所有Git镜像源
  const allGitMirrors = mirrorManager.getMirrors('git')
  
  // 加载用户的自定义镜像源
  const customMirrors = config.customGitMirrors || []
  const combinedMirrors = [...allGitMirrors, ...customMirrors]
  
  // 优先使用用户选择的镜像源
  const selectedMirror = combinedMirrors.find(m => m.key === config.selectedGitMirror)
  let mirrorsToTry = selectedMirror ? [selectedMirror] : []
  
  // 添加其他镜像源作为备选
  const otherMirrors = combinedMirrors.filter(m => m.key !== config.selectedGitMirror)
  mirrorsToTry = [...mirrorsToTry, ...otherMirrors]
  
  console.log('准备尝试的Git镜像源:', mirrorsToTry.map(m => m.name))
  
  for (let i = 0; i < mirrorsToTry.length; i++) {
    if (aborted.value) return false
    
    const mirror = mirrorsToTry[i]
    progressText.value = `正在使用 ${mirror.name} 更新代码... (${i + 1}/${mirrorsToTry.length})`
    
    try {
      console.log(`尝试使用镜像源: ${mirror.name} (${mirror.url})`)
      const result = await window.electronAPI.updateBackend(mirror.url)
      
      if (result.success) {
        console.log(`使用镜像源 ${mirror.name} 更新成功`)
        message.success(`使用 ${mirror.name} 更新代码成功`)
        return true
      } else {
        console.warn(`镜像源 ${mirror.name} 更新失败:`, result.error)
        if (i < mirrorsToTry.length - 1) {
          progressText.value = `${mirror.name} 失败，尝试下一个镜像源...`
          await new Promise(resolve => setTimeout(resolve, 1000)) // 等待1秒
        }
      }
    } catch (error) {
      console.error(`镜像源 ${mirror.name} 更新异常:`, error)
      if (i < mirrorsToTry.length - 1) {
        progressText.value = `${mirror.name} 异常，尝试下一个镜像源...`
        await new Promise(resolve => setTimeout(resolve, 1000)) // 等待1秒
      }
    }
  }
  
  console.error('所有Git镜像源都无法更新代码')
  return false
}

// 尝试安装依赖，支持镜像源重试
async function tryInstallDependenciesWithRetry(config: any): Promise<boolean> {
  // 获取所有PIP镜像源
  const allPipMirrors = mirrorManager.getMirrors('pip')
  
  // 优先使用用户选择的镜像源
  const selectedMirror = allPipMirrors.find(m => m.key === config.selectedPipMirror)
  let mirrorsToTry = selectedMirror ? [selectedMirror] : []
  
  // 添加其他镜像源作为备选
  const otherMirrors = allPipMirrors.filter(m => m.key !== config.selectedPipMirror)
  mirrorsToTry = [...mirrorsToTry, ...otherMirrors]
  
  console.log('准备尝试的PIP镜像源:', mirrorsToTry.map(m => m.name))
  
  for (let i = 0; i < mirrorsToTry.length; i++) {
    if (aborted.value) return false
    
    const mirror = mirrorsToTry[i]
    progressText.value = `正在使用 ${mirror.name} 安装依赖... (${i + 1}/${mirrorsToTry.length})`
    
    try {
      console.log(`尝试使用PIP镜像源: ${mirror.name} (${mirror.url})`)
      const result = await window.electronAPI.installDependencies(mirror.key)
      
      if (result.success) {
        console.log(`使用PIP镜像源 ${mirror.name} 安装成功`)
        message.success(`使用 ${mirror.name} 安装依赖成功`)
        return true
      } else {
        console.warn(`PIP镜像源 ${mirror.name} 安装失败:`, result.error)
        if (i < mirrorsToTry.length - 1) {
          progressText.value = `${mirror.name} 失败，尝试下一个镜像源...`
          await new Promise(resolve => setTimeout(resolve, 1000)) // 等待1秒
        }
      }
    } catch (error) {
      console.error(`PIP镜像源 ${mirror.name} 安装异常:`, error)
      if (i < mirrorsToTry.length - 1) {
        progressText.value = `${mirror.name} 异常，尝试下一个镜像源...`
        await new Promise(resolve => setTimeout(resolve, 1000)) // 等待1秒
      }
    }
  }
  
  console.error('所有PIP镜像源都无法安装依赖')
  return false
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

// 组件挂载时开始自动流程
onMounted(() => {
  aborted.value = false
  currentRetryCount.value = 0
  startAutoProcess()
})

// 组件卸载时清理定时器
onUnmounted(() => {
  clearTimers()
})
</script>

<style scoped>
.auto-mode {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 120px); /* 减去标题栏和一些边距 */
  padding: 20px;
  box-sizing: border-box;
}

.header {
  text-align: center;
  margin-bottom: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.header h1 {
  font-size: 38px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 8px;
}

.logo {
  width: 100px;
  height: 100px;
}

.tip {
  margin-bottom: 20px;
  text-align: center;
}

.auto-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  margin: 40px 0;
  width: 100%;
  max-width: 400px;
}

.progress-text {
  font-size: 16px;
  color: var(--ant-color-text);
  text-align: center;
}

.auto-actions {
  margin-top: 20px;
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
}

/* 重试倒计时样式 */
.retry-countdown {
  width: 100%;
  margin-top: 16px;
}

.retry-actions {
  margin-top: 12px;
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}

.retry-actions .ant-btn {
  min-width: 100px;
}

/* 响应式优化 */
@media (max-height: 700px) {
  .auto-mode {
    min-height: auto;
    padding: 10px;
  }
  
  .header {
    margin-bottom: 20px;
  }
  
  .header h1 {
    font-size: 32px;
  }
  
  .logo {
    width: 80px;
    height: 80px;
  }
}

@media (max-width: 600px) {
  .auto-actions {
    flex-direction: column;
    align-items: center;
  }
  
  .auto-actions .ant-btn {
    width: 200px;
  }
}
</style>
