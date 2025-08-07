<template>
  <div class="initialization-container">
    <!-- 管理员权限检查 -->
    <div v-if="!isAdmin" class="admin-check">
      <a-result
        status="warning"
        title="需要管理员权限"
        sub-title="为了正常安装和配置环境，请以管理员权限运行此应用"
      >
        <template #extra>
          <a-button type="primary" @click="restartAsAdmin">
            重新以管理员权限启动
          </a-button>
        </template>
      </a-result>
    </div>

    <!-- 自动初始化模式 -->
    <div v-else-if="autoMode" class="auto-mode">
      <div class="header">
        <h1>AUTO MAA 自动初始化</h1>
        <p>检测到环境已配置，正在自动启动...</p>
      </div>

      <div class="auto-progress">
        <a-spin size="large" />
        <div class="progress-text">{{ autoProgressText }}</div>
        <a-progress :percent="autoProgress" :status="autoProgressStatus" />
      </div>

      <div class="auto-actions">
        <a-button @click="switchToManualMode">切换到手动模式</a-button>
      </div>
    </div>

    <!-- 手动初始化模式 -->
    <div v-else class="manual-mode">
      <div class="header">
        <h1>AUTO MAA 初始化向导</h1>
        <p>欢迎使用 AUTO MAA，让我们来配置您的运行环境</p>
        
        <div class="header-actions">
          <a-button size="large" type="primary" @click="skipToHome">
            跳转至首页（仅开发用）
          </a-button>
          <a-button size="large" type="default" @click="jumpToStep(6)" style="margin-left: 16px;">
            跳到启动服务（第七步）
          </a-button>
        </div>
      </div>

      <a-steps 
        :current="currentStep" 
        :status="stepStatus"
        class="init-steps"
      >
        <a-step title="主题设置" description="选择您喜欢的主题" />
        <a-step title="Python 环境" description="安装 Python 运行环境" />
        <a-step title="pip 安装" description="安装 Python 包管理器" />
        <a-step title="Git 工具" description="安装 Git 版本控制工具" />
        <a-step title="源码获取" description="获取最新的后端代码" />
        <a-step title="依赖安装" description="安装 Python 依赖包" />
        <a-step title="启动服务" description="启动后端服务" />
      </a-steps>

      <!-- 全局进度条 -->
      <div v-if="isProcessing" class="global-progress">
        <a-progress 
          :percent="globalProgress" 
          :status="globalProgressStatus"
          :show-info="true"
        />
        <div class="progress-text">{{ progressText }}</div>
      </div>

      <div class="step-content">
        <!-- 步骤 0: 主题设置 -->
        <ThemeStep v-if="currentStep === 0" ref="themeStepRef" />

        <!-- 步骤 1: Python 环境 -->
        <PythonStep v-if="currentStep === 1" :python-installed="pythonInstalled" ref="pythonStepRef" />

        <!-- 步骤 2: pip 安装 -->
        <PipStep v-if="currentStep === 2" :pip-installed="pipInstalled" />

        <!-- 步骤 3: Git 工具 -->
        <GitStep v-if="currentStep === 3" :git-installed="gitInstalled" />

        <!-- 步骤 4: 源码获取 -->
        <BackendStep v-if="currentStep === 4" :backend-exists="backendExists" ref="backendStepRef" />

        <!-- 步骤 5: 依赖安装 -->
        <DependenciesStep v-if="currentStep === 5" ref="dependenciesStepRef" />

        <!-- 步骤 6: 启动服务 -->
        <ServiceStep v-if="currentStep === 6" ref="serviceStepRef" />
      </div>

      <div class="step-actions">
        <a-button 
          v-if="currentStep > 0" 
          @click="prevStep"
          :disabled="isProcessing"
        >
          上一步
        </a-button>
        
        <a-button 
          v-if="currentStep < 6" 
          type="primary" 
          @click="nextStep"
          :loading="isProcessing"
        >
          {{ getNextButtonText() }}
        </a-button>
        
        <!-- 第7步启动服务按钮 -->
        <a-button 
          v-if="currentStep === 6 && !serviceStarted" 
          type="primary" 
          @click="nextStep"
          :loading="isProcessing"
        >
          启动服务
        </a-button>
        
        <!-- 服务启动完成后的进入应用按钮 -->
        <a-button 
          v-if="currentStep === 6 && serviceStarted" 
          type="primary" 
          @click="enterApp"
        >
          进入应用
        </a-button>
      </div>

      <div v-if="errorMessage" class="error-message">
        <a-alert 
          :message="errorMessage" 
          type="error" 
          show-icon 
          closable
          @close="errorMessage = ''"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { createComponentLogger } from '@/utils/logger'
import { getConfig, saveConfig, setInitialized } from '@/utils/config'
import ThemeStep from '@/components/initialization/ThemeStep.vue'
import PythonStep from '@/components/initialization/PythonStep.vue'
import PipStep from '@/components/initialization/PipStep.vue'
import GitStep from '@/components/initialization/GitStep.vue'
import BackendStep from '@/components/initialization/BackendStep.vue'
import DependenciesStep from '@/components/initialization/DependenciesStep.vue'
import ServiceStep from '@/components/initialization/ServiceStep.vue'
import type { DownloadProgress } from '@/types/initialization'

const router = useRouter()
const logger = createComponentLogger('InitializationNew')

// 基础状态
const currentStep = ref(0)
const stepStatus = ref<'wait' | 'process' | 'finish' | 'error'>('process')
const errorMessage = ref('')
const isProcessing = ref(false)
const isAdmin = ref(true)

// 模式控制
const autoMode = ref(false)
const autoProgress = ref(0)
const autoProgressText = ref('')
const autoProgressStatus = ref<'normal' | 'exception' | 'success'>('normal')

// 安装状态
const pythonInstalled = ref(false)
const pipInstalled = ref(false)
const gitInstalled = ref(false)
const backendExists = ref(false)
const dependenciesInstalled = ref(false)
const serviceStarted = ref(false)

// 全局进度条状态
const globalProgress = ref(0)
const globalProgressStatus = ref<'normal' | 'exception' | 'success'>('normal')
const progressText = ref('')

// 组件引用
const themeStepRef = ref()
const pythonStepRef = ref()
const backendStepRef = ref()
const dependenciesStepRef = ref()
const serviceStepRef = ref()

// 计算属性
const allCompleted = computed(() => 
  pythonInstalled.value && pipInstalled.value && gitInstalled.value && 
  backendExists.value && dependenciesInstalled.value && serviceStarted.value
)

// 基础功能函数
function skipToHome() {
  router.push('/home')
}

function jumpToStep(step: number) {
  currentStep.value = step
}

function switchToManualMode() {
  autoMode.value = false
}

async function restartAsAdmin() {
  try {
    await window.electronAPI.restartAsAdmin()
  } catch (error) {
    logger.error('重启为管理员失败', error)
  }
}

// 步骤控制
function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

async function nextStep() {
  console.log('nextStep 被调用，当前步骤:', currentStep.value)
  isProcessing.value = true
  errorMessage.value = ''
  
  try {
    switch (currentStep.value) {
      case 0: // 主题设置
        console.log('执行主题设置')
        themeStepRef.value?.saveSettings()
        break
      case 1: // Python 环境
        console.log('执行Python环境安装')
        if (!pythonInstalled.value) {
          await installPython()
        }
        break
      case 2: // pip 安装
        console.log('执行pip安装')
        if (!pipInstalled.value) {
          await installPip()
        }
        break
      case 3: // Git 工具
        console.log('执行Git工具安装')
        if (!gitInstalled.value) {
          await installGit()
        }
        break
      case 4: // 源码获取
        console.log('执行源码获取')
        if (!backendExists.value) {
          await cloneBackend()
        } else {
          await updateBackend()
        }
        break
      case 5: // 依赖安装
        console.log('执行依赖安装')
        if (!dependenciesInstalled.value) {
          await installDependencies()
        }
        break
      case 6: // 启动服务
        console.log('执行启动服务')
        await startBackendService()
        break
    }
    
    if (currentStep.value < 6) {
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
    case 0: return '下一步'
    case 1: return pythonInstalled.value ? '下一步' : '安装 Python'
    case 2: return pipInstalled.value ? '下一步' : '安装 pip'
    case 3: return gitInstalled.value ? '下一步' : '安装 Git'
    case 4: return backendExists.value ? '更新代码' : '获取代码'
    case 5: return '安装依赖'
    case 6: return '启动服务'
    default: return '下一步'
  }
}

// 自动开始测速
async function autoStartSpeedTest() {
  // 延迟一下确保组件已经挂载
  setTimeout(async () => {
    switch (currentStep.value) {
      case 1: // Python 环境
        if (!pythonInstalled.value && pythonStepRef.value?.testPythonMirrorSpeed) {
          console.log('自动开始Python镜像测速')
          await pythonStepRef.value.testPythonMirrorSpeed()
        }
        break
      case 4: // 源码获取
        if (backendStepRef.value?.testGitMirrorSpeed) {
          console.log('自动开始Git镜像测速')
          await backendStepRef.value.testGitMirrorSpeed()
        }
        break
      case 5: // 依赖安装
        if (!dependenciesInstalled.value && dependenciesStepRef.value?.testPipMirrorSpeed) {
          console.log('自动开始pip镜像测速')
          await dependenciesStepRef.value.testPipMirrorSpeed()
        }
        break
    }
  }, 500) // 延迟500ms确保组件完全加载
}

// 安装函数
async function installPython() {
  logger.info('开始安装Python')
  const mirror = pythonStepRef.value?.selectedPythonMirror || 'tsinghua'
  const result = await window.electronAPI.downloadPython(mirror)
  if (result.success) {
    logger.info('Python安装成功')
    pythonInstalled.value = true
    saveConfig({ pythonInstalled: true })
  } else {
    logger.error('Python安装失败', result.error)
    throw new Error(result.error)
  }
}

async function installPip() {
  logger.info('开始安装pip')
  const result = await window.electronAPI.installPip()
  if (result.success) {
    logger.info('pip安装成功')
    pipInstalled.value = true
    saveConfig({ pipInstalled: true })
  } else {
    logger.error('pip安装失败', result.error)
    throw new Error(result.error)
  }
}

async function installGit() {
  logger.info('开始安装Git工具')
  const result = await window.electronAPI.downloadGit()
  if (result.success) {
    logger.info('Git工具安装成功')
    gitInstalled.value = true
    saveConfig({ gitInstalled: true })
  } else {
    logger.error('Git工具安装失败', result.error)
    throw new Error(result.error)
  }
}

async function cloneBackend() {
  const selectedMirror = backendStepRef.value?.selectedGitMirror || 'github'
  const mirror = backendStepRef.value?.gitMirrors?.find((m: any) => m.key === selectedMirror)
  logger.info('开始克隆后端代码', { mirror: mirror?.name, url: mirror?.url })
  const result = await window.electronAPI.cloneBackend(mirror?.url)
  if (result.success) {
    logger.info('后端代码克隆成功')
    backendExists.value = true
    saveConfig({ backendExists: true })
  } else {
    logger.error('后端代码克隆失败', result.error)
    throw new Error(result.error)
  }
}

async function updateBackend() {
  const selectedMirror = backendStepRef.value?.selectedGitMirror || 'github'
  const mirror = backendStepRef.value?.gitMirrors?.find((m: any) => m.key === selectedMirror)
  logger.info('开始更新后端代码', { mirror: mirror?.name, url: mirror?.url })
  const result = await window.electronAPI.updateBackend(mirror?.url)
  if (!result.success) {
    logger.error('后端代码更新失败', result.error)
    throw new Error(result.error)
  }
  logger.info('后端代码更新成功')
}

async function installDependencies() {
  logger.info('开始安装Python依赖')
  const mirror = dependenciesStepRef.value?.selectedPipMirror || 'tsinghua'
  const result = await window.electronAPI.installDependencies(mirror)
  if (result.success) {
    logger.info('Python依赖安装成功')
    dependenciesInstalled.value = true
    saveConfig({ dependenciesInstalled: true })
  } else {
    logger.error('Python依赖安装失败', result.error)
    throw new Error(result.error)
  }
}

async function startBackendService() {
  logger.info('开始启动后端服务')
  
  if (serviceStepRef.value) {
    serviceStepRef.value.startingService = true
    serviceStepRef.value.showServiceProgress = true
    serviceStepRef.value.serviceStatus = '正在启动后端服务...'
  }
  
  try {
    const result = await window.electronAPI.startBackend()
    if (result.success) {
      if (serviceStepRef.value) {
        serviceStepRef.value.serviceProgress = 100
        serviceStepRef.value.serviceStatus = '后端服务启动成功'
      }
      serviceStarted.value = true
      stepStatus.value = 'finish'
      logger.info('后端服务启动成功')
    } else {
      logger.error('后端服务启动失败', result.error)
      throw new Error(result.error)
    }
  } catch (error) {
    if (serviceStepRef.value) {
      serviceStepRef.value.serviceStatus = '后端服务启动失败'
    }
    logger.error('后端服务启动异常', error)
    throw error
  } finally {
    if (serviceStepRef.value) {
      serviceStepRef.value.startingService = false
    }
  }
}

// 进入应用
async function enterApp() {
  try {
    // 设置初始化完成标记
    await setInitialized(true)
    console.log('设置初始化完成标记，跳转到首页')
    router.push('/home')
  } catch (error) {
    console.error('进入应用失败:', error)
    errorMessage.value = '保存配置失败，请重试'
  }
}

// 检查环境状态
async function checkEnvironment() {
  try {
    logger.info('开始检查环境状态')
    const status = await window.electronAPI.checkEnvironment()
    
    logger.info('环境检查结果', status)
    console.log('环境检查结果:', status)
    
    pythonInstalled.value = status.pythonExists
    gitInstalled.value = status.gitExists
    backendExists.value = status.backendExists
    dependenciesInstalled.value = status.dependenciesInstalled
    
    // 检查配置文件中的状态
    const config = await getConfig()
    pipInstalled.value = config.pipInstalled || false
    
    // 更新配置文件中的状态，确保与实际环境一致
    const needsUpdate = 
      config.pythonInstalled !== status.pythonExists ||
      config.gitInstalled !== status.gitExists ||
      config.backendExists !== status.backendExists ||
      config.dependenciesInstalled !== status.dependenciesInstalled
    
    if (needsUpdate) {
      console.log('更新配置文件中的环境状态')
      await saveConfig({
        pythonInstalled: status.pythonExists,
        gitInstalled: status.gitExists,
        backendExists: status.backendExists,
        dependenciesInstalled: status.dependenciesInstalled
      })
    }
    
    // 检查是否第一次启动
    const isFirst = config.isFirstLaunch
    console.log('是否第一次启动:', isFirst)
    
    // 检查是否应该进入自动模式
    console.log('自动模式判断条件:')
    console.log('- 不是第一次启动:', !isFirst)
    console.log('- 配置显示已初始化:', config.init)
    console.log('- 环境检查结果:', status.isInitialized)
    
    // 如果配置显示已初始化且不是第一次启动，进入自动模式
    // 不再依赖环境检查结果，因为配置文件更准确
    if (!isFirst && config.init) {
      logger.info('非首次启动且配置显示已初始化，进入自动模式')
      console.log('进入自动模式，开始自动启动流程')
      autoMode.value = true
      await autoStartProcess()
    } else {
      logger.info('首次启动或配置显示未初始化，进入手动模式')
      console.log('进入手动模式，当前步骤:', currentStep.value)
      console.log('原因: isFirst =', isFirst, ', config.init =', config.init)
      
      // 如果是首次启动，从主题设置开始
      if (isFirst) {
        currentStep.value = 0
        console.log('首次启动，从主题设置开始')
      }
    }
  } catch (error) {
    const errorMsg = `环境检查失败: ${error instanceof Error ? error.message : String(error)}`
    logger.error('环境检查失败', error)
    console.error('环境检查失败:', error)
    errorMessage.value = errorMsg
  }
}

// 自动启动流程
async function autoStartProcess() {
  try {
    // 获取配置中保存的镜像源设置
    const config = await getConfig()
    
    autoProgressText.value = '检查Git仓库更新...'
    autoProgress.value = 20
    
    // 检查Git仓库是否有更新
    const hasUpdate = await checkGitUpdate()
    
    if (hasUpdate) {
      autoProgressText.value = '发现更新，正在更新代码...'
      autoProgress.value = 40
      
      // 使用配置中保存的Git镜像源
      const gitMirrorUrl = getGitMirrorUrl(config.selectedGitMirror)
      const result = await window.electronAPI.updateBackend(gitMirrorUrl)
      if (!result.success) {
        throw new Error(`代码更新失败: ${result.error}`)
      }
      
      autoProgressText.value = '更新依赖包...'
      autoProgress.value = 60
      
      // 使用配置中保存的pip镜像源
      const pipResult = await window.electronAPI.installDependencies(config.selectedPipMirror)
      if (!pipResult.success) {
        throw new Error(`依赖更新失败: ${pipResult.error}`)
      }
    }
    
    autoProgressText.value = '启动后端服务...'
    autoProgress.value = 80
    await startBackendService()
    
    autoProgressText.value = '启动完成！'
    autoProgress.value = 100
    autoProgressStatus.value = 'success'
    
    logger.info('自动启动流程完成，即将进入应用')
    
    // 延迟2秒后自动进入应用
    setTimeout(() => {
      enterApp()
    }, 2000)
    
  } catch (error) {
    logger.error('自动启动流程失败', error)
    autoProgressText.value = `自动启动失败: ${error instanceof Error ? error.message : String(error)}`
    autoProgressStatus.value = 'exception'
    
    // 5秒后提供切换到手动模式的选项
    setTimeout(() => {
      if (autoProgressStatus.value === 'exception') {
        autoProgressText.value = '自动启动失败，请点击下方按钮切换到手动模式'
      }
    }, 5000)
  }
}

// 根据镜像源key获取对应的URL
function getGitMirrorUrl(mirrorKey: string): string {
  const mirrors = {
    github: 'https://github.com/DLmaster361/AUTO_MAA.git',
    ghfast: 'https://ghfast.top/https://github.com/DLmaster361/AUTO_MAA.git'
  }
  return mirrors[mirrorKey as keyof typeof mirrors] || mirrors.github
}

// 检查Git更新（简化版本，实际可以调用Git API）
async function checkGitUpdate(): Promise<boolean> {
  // 这里可以实现更复杂的Git更新检查逻辑
  // 暂时返回false，表示没有更新
  return false
}

// 检查管理员权限
async function checkAdminPermission() {
  try {
    const adminStatus = await window.electronAPI.checkAdmin()
    isAdmin.value = adminStatus
    console.log('管理员权限检查结果:', adminStatus)
  } catch (error) {
    logger.error('检查管理员权限失败', error)
    isAdmin.value = false
  }
}

// 监听下载进度
function handleDownloadProgress(progress: DownloadProgress) {
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
  
  // 更新自动模式进度
  if (autoMode.value) {
    autoProgress.value = progress.progress
    autoProgressText.value = progress.message
  }
}

onMounted(async () => {
  console.log('初始化页面 onMounted 开始')
  
  // 测试配置系统
  try {
    console.log('测试配置系统...')
    const testConfig = await getConfig()
    console.log('当前配置:', testConfig)
    
    // 测试保存配置
    await saveConfig({ isFirstLaunch: false })
    console.log('测试配置保存成功')
    
    // 重新读取配置验证
    const updatedConfig = await getConfig()
    console.log('更新后的配置:', updatedConfig)
  } catch (error) {
    console.error('配置系统测试失败:', error)
  }
  
  // 检查管理员权限
  await checkAdminPermission()
  
  if (isAdmin.value) {
    // 延迟检查环境，确保页面完全加载
    setTimeout(async () => {
      console.log('开始环境检查')
      await checkEnvironment()
    }, 100)
  }
  
  window.electronAPI.onDownloadProgress(handleDownloadProgress)
  console.log('初始化页面 onMounted 完成')
})

onUnmounted(() => {
  window.electronAPI.removeDownloadProgressListener()
})
</script>

<style scoped>
.initialization-container {
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
  padding: 50px 100px;
  margin: 0 auto;
}

.admin-check {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 60vh;
}

.auto-mode {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}

.auto-progress {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  margin: 40px 0;
  width: 400px;
}

.progress-text {
  font-size: 16px;
  color: var(--ant-color-text);
  text-align: center;
}

.auto-actions {
  margin-top: 20px;
}

.manual-mode .header {
  text-align: center;
  margin-bottom: 40px;
}

.header h1 {
  font-size: 28px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 8px;
}

.header p {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 20px 0;
}

.header-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
}

.init-steps {
  margin-bottom: 40px;
}

.step-content {
  min-height: 300px;
  margin-bottom: 40px;
}

.step-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.error-message {
  margin-top: 20px;
}

.global-progress {
  margin: 20px 0;
  padding: 20px;
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border);
}

.global-progress .progress-text {
  text-align: center;
  margin-top: 8px;
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

@media (max-width: 768px) {
  .initialization-container {
    padding: 20px;
  }
  
  .header-actions {
    flex-direction: column;
    gap: 8px;
  }
  
  .step-actions {
    flex-direction: column;
    gap: 12px;
  }
}
</style>