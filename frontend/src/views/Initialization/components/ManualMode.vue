<template>
  <div class="manual-mode">
    <div class="header">
      <!--      <a-typography-title>AUTO-MAS 初始化向导</a-typography-title>-->
      <a-typography-title :level="3"
        >欢迎使用 AUTO-MAS，让我们来配置您的运行环境</a-typography-title
      >

      <!--            <div class="header-actions">-->
      <!--              <a-button size="large" type="prim  try {
    const result = await window.electronAPI.startBackend()
    if (result.success) {
      if (serviceStepRef.value) {
        serviceStepRef.value.serviceProgress = 100
        serviceStepRef.value.serviceStatus = '后端服务启动成功，正在建立WebSocket连接...'
      }
      
      // 后端启动成功，建立WebSocket连接
      console.log('后端启动成功，正在建立WebSocket连接...')
      const wsConnected = await connectAfterBackendStart()
      if (!wsConnected) {
        console.warn('WebSocket连接建立失败，但继续进入应用')
      } else {
        console.log('WebSocket连接建立成功')
      }
      
      if (serviceStepRef.value) {
        serviceStepRef.value.serviceStatus = '后端服务启动成功，即将进入主页...'
      }
      stepStatus.value = 'finish'
      console.log('后端服务启动成功，延迟1秒后自动进入主页')

      // 延迟1秒后自动进入主页
      setTimeout(() => {
        handleEnterApp()
      }, 1000)
    } else {ndleSkipToHome">-->
      <!--                跳转至首页（仅开发用）-->
      <!--              </a-button>-->
      <!--              <a-button-->
      <!--                size="large"-->
      <!--                type="default"-->
      <!--                @click="handleJumpToStep(3)"-->
      <!--                style="margin-left: 16px"-->
      <!--              >-->
      <!--                跳到启动服务（第六步）-->
      <!--              </a-button>-->
      <!--            </div>-->
    </div>

    <a-steps :current="displayCurrentStep" :status="stepStatus" class="init-steps">
      <a-step title="设置主题" />
      <a-step title="配置环境" />
      <a-step title="Git 工具" />
      <a-step title="获取源码" />
      <a-step title="安装依赖" />
      <a-step title="启动服务" />
    </a-steps>

    <!--    &lt;!&ndash; 全局进度条 &ndash;&gt;-->
    <!--    <div v-if="isProcessing" class="global-progress">-->
    <!--      <a-progress -->
    <!--        :percent="globalProgress" -->
    <!--        :status="globalProgressStatus"-->
    <!--        :show-info="true"-->
    <!--      />-->
    <!--      <div class="progress-text">{{ progressText }}</div>-->
    <!--    </div>-->

    <div class="step-content">
      <!-- 步骤 0: 主题设置 -->
      <ThemeStep v-if="currentStep === 0" ref="themeStepRef" />

      <!-- 步骤 1: Python 环境 -->
      <PythonStep
        v-if="currentStep === 1"
        ref="pythonStepRef"
        :python-installed="pythonInstalled"
      />

      <!-- 步骤 2: Git 工具 -->
      <GitStep v-if="currentStep === 2" ref="gitStepRef" :git-installed="gitInstalled" />

      <!-- 步骤 3: 源码获取 -->
      <BackendStep v-if="currentStep === 3" ref="backendStepRef" :backend-exists="backendExists" />

      <!-- 步骤 4: 依赖安装 -->
      <DependenciesStep v-if="currentStep === 4" ref="dependenciesStepRef" />

      <!-- 步骤 5: 启动服务 -->
      <ServiceStep v-if="currentStep === 5" ref="serviceStepRef" />
    </div>

    <div class="step-actions">
      <a-button
        type="default"
        size="large"
        :disabled="currentStep === 0 || isProcessing"
        @click="handlePrevStep"
      >
        上一步
      </a-button>

      <a-button
        v-if="currentStep < 5"
        size="large"
        type="primary"
        :loading="isProcessing"
        @click="handleNextStep"
      >
        {{ getNextButtonText() }}
      </a-button>

      <!-- 第6步重新启动服务按钮 -->
      <a-button
        v-if="currentStep === 5"
        type="default"
        size="large"
        :loading="isProcessing"
        @click="handleNextStep"
      >
        重新启动服务
      </a-button>
    </div>

    <!--    <div v-if="errorMessage" class="error-message">-->
    <!--      <a-alert -->
    <!--        :message="errorMessage" -->
    <!--        type="error" -->
    <!--        show-icon -->
    <!--        closable-->
    <!--        @close="errorMessage = ''"-->
    <!--      />-->
    <!--    </div>-->
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { notification } from 'ant-design-vue'
import { saveConfig } from '@/utils/config.ts'
import { useUpdateChecker } from '@/composables/useUpdateChecker.ts'
import ThemeStep from './ThemeStep.vue'
import PythonStep from './PythonStep.vue'

import GitStep from './GitStep.vue'
import BackendStep from './BackendStep.vue'
import DependenciesStep from './DependenciesStep.vue'
import ServiceStep from './ServiceStep.vue'
import { connectAfterBackendStart } from '@/composables/useWebSocket.ts'

// Props
interface Props {
  // 状态
  pythonInstalled: boolean
  gitInstalled: boolean
  backendExists: boolean
  dependenciesInstalled: boolean
  serviceStarted: boolean

  // 事件处理函数
  onSkipToHome: () => void
  onEnterApp: () => void
  onProgressUpdate: (progress: { progress: number; status: string; message: string }) => void
}

const props = defineProps<Props>()

// 使用更新检查器
const { startPolling } = useUpdateChecker()

// 基础状态
const currentStep = ref(0)
const stepStatus = ref<'wait' | 'process' | 'finish' | 'error'>('process')
const errorMessage = ref('')
const isProcessing = ref(false)

// 显示的当前步骤就是实际步骤
const displayCurrentStep = computed(() => {
  return currentStep.value
})

// 全局进度条状态
const globalProgress = ref(0)
const globalProgressStatus = ref<'normal' | 'exception' | 'success'>('normal')
const progressText = ref('')

// 组件引用
const themeStepRef = ref()
const pythonStepRef = ref()
const gitStepRef = ref()
const backendStepRef = ref()
const dependenciesStepRef = ref()
const serviceStepRef = ref()

// 事件处理
function handleJumpToStep(step: number) {
  currentStep.value = step
}

function handleEnterApp() {
  props.onEnterApp()
}

// 步骤控制
function handlePrevStep() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

async function handleNextStep() {
  console.log('nextStep 被调用，当前步骤:', currentStep.value)
  isProcessing.value = true
  errorMessage.value = ''

  try {
    switch (currentStep.value) {
      case 0: // 主题设置
        console.log('执行主题设置')
        await themeStepRef.value?.saveSettings()
        break
      case 1: // Python 环境
        console.log('执行Python环境安装')
        if (!props.pythonInstalled) {
          await installPython()
        }
        break
      case 2: // Git 工具
        console.log('执行Git工具安装')
        if (!props.gitInstalled) {
          await installGit()
        }
        break
      case 3: // 源码获取
        console.log('执行源码获取')
        if (!props.backendExists) {
          await cloneBackend()
        } else {
          await updateBackend()
        }
        break
      case 4: // 依赖安装
        console.log('执行依赖安装')
        // 总是执行依赖安装，确保环境完整
        await installDependencies()
        break
      case 5: // 启动服务
        console.log('执行启动服务')
        await startBackendService()
        break
    }

    if (currentStep.value < 5) {
      currentStep.value++
      // 进入新步骤时自动开始测速
      await autoStartSpeedTest()
    }
  } catch (error) {
    console.error('nextStep 执行出错:', error)
    errorMessage.value = error instanceof Error ? error.message : String(error)
    stepStatus.value = 'error'
  } finally {
    isProcessing.value = false
  }
}

function getNextButtonText() {
  switch (currentStep.value) {
    case 0:
      return '下一步'
    case 1:
      return props.pythonInstalled ? '下一步' : '安装 Python'
    case 2:
      return props.gitInstalled ? '下一步' : '安装 Git'
    case 3:
      return props.backendExists ? '更新代码' : '获取代码'
    case 4:
      return props.dependenciesInstalled ? '重新安装依赖' : '安装依赖'
    case 5:
      return '启动服务'
    default:
      return '下一步'
  }
}

// 自动开始测速和自动启动服务
async function autoStartSpeedTest() {
  // 延迟一下确保组件已经挂载
  setTimeout(async () => {
    switch (currentStep.value) {
      case 1: // Python 环境
        if (!props.pythonInstalled && pythonStepRef.value?.testPythonMirrorSpeed) {
          console.log('自动开始Python镜像测速')
          await pythonStepRef.value.testPythonMirrorSpeed()
        }
        break
      case 3: // 源码获取
        if (backendStepRef.value?.testGitMirrorSpeed) {
          console.log('自动开始Git镜像测速')
          await backendStepRef.value.testGitMirrorSpeed()
        }
        break
      case 4: // 依赖安装
        if (!props.dependenciesInstalled && dependenciesStepRef.value?.testPipMirrorSpeed) {
          console.log('自动开始pip镜像测速')
          await dependenciesStepRef.value.testPipMirrorSpeed()
        }
        break
      case 5: // 启动服务 - 自动启动后端
        console.log('进入第六步，自动启动后端服务')
        await autoStartBackendService()
        break
    }
  }, 500) // 延迟500ms确保组件完全加载
}

// 安装函数
async function installPython() {
  console.log('开始安装Python')
  const mirror = pythonStepRef.value?.selectedPythonMirror || 'tsinghua'
  const result = await window.electronAPI.downloadPython(mirror)
  if (result.success) {
    console.log('Python安装成功')
    await saveConfig({ pythonInstalled: true })
  } else {
    console.error('Python安装失败', result.error)
    throw new Error(result.error)
  }
}

async function installGit() {
  console.log('开始安装Git工具')
  const result = await window.electronAPI.downloadGit()
  if (result.success) {
    console.log('Git工具安装成功')
    await saveConfig({ gitInstalled: true })
  } else {
    console.error('Git工具安装失败', result.error)
    throw new Error(result.error)
  }
}

async function cloneBackend() {
  const selectedMirror = backendStepRef.value?.selectedGitMirror || 'github'
  const mirror = backendStepRef.value?.gitMirrors?.find((m: any) => m.key === selectedMirror)
  console.log('开始克隆后端代码', { mirror: mirror?.name, url: mirror?.url })
  const result = await window.electronAPI.cloneBackend(mirror?.url)
  if (result.success) {
    console.log('后端代码克隆成功')
    await saveConfig({ backendExists: true })
  } else {
    console.error('后端代码克隆失败', result.error)
    throw new Error(result.error)
  }
}

async function updateBackend() {
  const selectedMirror = backendStepRef.value?.selectedGitMirror || 'github'
  const mirror = backendStepRef.value?.gitMirrors?.find((m: any) => m.key === selectedMirror)
  console.log('开始更新后端代码', { mirror: mirror?.name, url: mirror?.url })
  const result = await window.electronAPI.updateBackend(mirror?.url)
  if (!result.success) {
    console.error('后端代码更新失败', result.error)
    throw new Error(result.error)
  }
  console.log('后端代码更新成功')
}

async function installDependencies() {
  console.log('开始安装Python依赖')
  const mirror = dependenciesStepRef.value?.selectedPipMirror || 'tsinghua'
  const result = await window.electronAPI.installDependencies(mirror)
  if (result.success) {
    console.log('Python依赖安装成功')
    await saveConfig({ dependenciesInstalled: true })
  } else {
    console.error('Python依赖安装失败', result.error)
    throw new Error(result.error)
  }
}

// 自动启动后端服务（进入第七步时调用）
async function autoStartBackendService() {
  console.log('自动启动后端服务')
  isProcessing.value = true
  errorMessage.value = ''

  if (serviceStepRef.value) {
    serviceStepRef.value.startingService = true
    serviceStepRef.value.showServiceProgress = true
    serviceStepRef.value.serviceStatus = '正在自动启动后端服务...'
  }

  try {
    const result = await window.electronAPI.startBackend()
    if (result.success) {
      if (serviceStepRef.value) {
        serviceStepRef.value.serviceProgress = 100
        serviceStepRef.value.serviceStatus = '后端服务启动成功，正在建立WebSocket连接...'
      }

      // 后端启动成功，建立WebSocket连接
      console.log('后端自动启动成功，正在建立WebSocket连接...')
      const wsConnected = await connectAfterBackendStart()
      if (!wsConnected) {
        console.warn('WebSocket连接建立失败，但继续进入应用')
      } else {
        console.log('WebSocket连接建立成功')
      }

      // WebSocket连接完成后，启动版本检查定时任务
      console.log('启动版本检查定时任务...')
      await startPolling()

      if (serviceStepRef.value) {
        serviceStepRef.value.serviceStatus = '后端服务启动成功，即将进入主页...'
      }
      stepStatus.value = 'finish'
      console.log('后端服务自动启动成功，延迟1秒后自动进入主页')

      // 延迟1秒后自动进入主页
      setTimeout(() => {
        handleEnterApp()
      }, 1000)
    } else {
      console.error('后端服务自动启动失败', result.error)
      if (serviceStepRef.value) {
        serviceStepRef.value.serviceStatus = '后端服务启动失败，请点击重新启动'
      }
      errorMessage.value = `后端服务启动失败: ${result.error}`
    }
  } catch (error) {
    if (serviceStepRef.value) {
      serviceStepRef.value.serviceStatus = '后端服务启动失败，请点击重新启动'
    }
    console.error('后端服务自动启动异常', error)
    errorMessage.value = error instanceof Error ? error.message : String(error)
  } finally {
    if (serviceStepRef.value) {
      serviceStepRef.value.startingService = false
    }
    isProcessing.value = false
  }
}

// 手动启动后端服务（用户点击按钮时调用）
async function startBackendService() {
  console.log('手动重新启动后端服务')

  if (serviceStepRef.value) {
    serviceStepRef.value.startingService = true
    serviceStepRef.value.showServiceProgress = true
    serviceStepRef.value.serviceStatus = '正在重新启动后端服务...'
  }

  try {
    const result = await window.electronAPI.startBackend()
    if (result.success) {
      if (serviceStepRef.value) {
        serviceStepRef.value.serviceProgress = 100
        serviceStepRef.value.serviceStatus = '后端服务启动成功，正在建立WebSocket连接...'
      }

      // 后端启动成功，建立WebSocket连接
      console.log('后端手动启动成功，正在建立WebSocket连接...')
      const wsConnected = await connectAfterBackendStart()
      if (!wsConnected) {
        console.warn('WebSocket连接建立失败，但继续进入应用')
      } else {
        console.log('WebSocket连接建立成功')
      }

      // WebSocket连接完成后，启动版本检查定时任务
      console.log('启动版本检查定时任务...')
      await startPolling()

      if (serviceStepRef.value) {
        serviceStepRef.value.serviceStatus = '后端服务启动成功，即将进入主页...'
      }
      stepStatus.value = 'finish'
      console.log('后端服务手动启动成功，延迟1秒后自动进入主页')

      // 延迟1秒后自动进入主页
      setTimeout(() => {
        handleEnterApp()
      }, 1000)
    } else {
      console.error('后端服务手动启动失败', result.error)
      throw new Error(result.error)
    }
  } catch (error) {
    if (serviceStepRef.value) {
      serviceStepRef.value.serviceStatus = '后端服务启动失败'
    }
    console.error('后端服务手动启动异常', error)
    throw error
  } finally {
    if (serviceStepRef.value) {
      serviceStepRef.value.startingService = false
    }
  }
}

// 监听下载进度
function handleDownloadProgress(progress: any) {
  // 更新全局进度条
  globalProgress.value = progress.progress
  progressText.value = progress.message

  if (progress.status === 'error') {
    globalProgressStatus.value = 'exception'
  } else if (progress.status === 'completed') {
    globalProgressStatus.value = 'success'
  } else {
    globalProgressStatus.value = 'normal'
  }

  // 通知父组件
  props.onProgressUpdate(progress)
}

// 暴露给父组件的方法
defineExpose({
  currentStep,
  handleDownloadProgress,
})
// 监听 errorMessage，一旦有内容就弹窗
watch(errorMessage, val => {
  if (val) {
    notification.error({
      message: '出错啦~',
      description: val,
      duration: 4.5,
    })
    // 弹窗后可选：自动清空 errorMessage
    // errorMessage.value = ''
  }
})
</script>

<style scoped>
.manual-mode {
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
}

.init-steps {
  margin-bottom: 20px;
}

.step-content {
  background-color: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 24px;
  min-height: 300px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.step-actions {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-top: 20px;
}

/* 响应式优化 */
@media (max-width: 768px) {
  .manual-mode {
    gap: 15px;
  }

  .header h3 {
    font-size: 20px;
  }

  .init-steps {
    /* 在小屏幕上，步骤条可以换行显示 */
    :deep(.ant-steps-item-title) {
      white-space: normal;
    }
  }

  .step-content {
    padding: 16px;
    min-height: 250px;
  }
}

@media (max-width: 480px) {
  .step-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
