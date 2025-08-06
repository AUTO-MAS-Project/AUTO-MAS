<template>
  <div class="initialization-container">
    <div class="initialization-content">
      <div class="header">
        <h1>AUTO MAA 初始化向导</h1>
        <p>欢迎使用 AUTO MAA，让我们来配置您的运行环境</p>
      </div>

      <a-steps 
        :current="currentStep" 
        :status="stepStatus"
        class="init-steps"
      >
        <a-step title="主题设置" description="选择您喜欢的主题" />
        <a-step title="Python 环境" description="安装 Python 运行环境" />
        <a-step title="Git 工具" description="安装 Git 版本控制工具" />
        <a-step title="源码获取" description="获取最新的后端代码" />
        <a-step title="依赖安装" description="安装 Python 依赖包" />
        <a-step title="启动服务" description="启动后端服务" />
      </a-steps>

      <div class="step-content">
        <!-- 步骤 0: 主题设置 -->
        <div v-if="currentStep === 0" class="step-panel">
          <h3>选择您的主题偏好</h3>
          <div class="theme-settings">
            <div class="setting-group">
              <label>主题模式</label>
              <a-radio-group v-model:value="selectedThemeMode" @change="onThemeModeChange">
                <a-radio-button value="light">浅色模式</a-radio-button>
                <a-radio-button value="dark">深色模式</a-radio-button>
                <a-radio-button value="system">跟随系统</a-radio-button>
              </a-radio-group>
            </div>
            <div class="setting-group">
              <label>主题色彩</label>
              <div class="color-picker">
                <div 
                  v-for="(color, key) in themeColors" 
                  :key="key"
                  class="color-option"
                  :class="{ active: selectedThemeColor === key }"
                  :style="{ backgroundColor: color }"
                  @click="onThemeColorChange(key)"
                />
              </div>
            </div>
          </div>
        </div>

        <!-- 步骤 1: Python 环境 -->
        <div v-if="currentStep === 1" class="step-panel">
          <h3>Python 运行环境</h3>
          <div v-if="!pythonInstalled" class="install-section">
            <p>需要安装 Python 3.13.0 运行环境（64位嵌入式版本）</p>
            
            <div class="mirror-grid">
              <div 
                v-for="mirror in pythonMirrors" 
                :key="mirror.key"
                class="mirror-card"
                :class="{ active: selectedPythonMirror === mirror.key }"
                @click="selectedPythonMirror = mirror.key"
              >
                <div class="mirror-header">
                  <h4>{{ mirror.name }}</h4>
                  <div class="speed-badge" :class="getSpeedClass(mirror.speed)">
                    <span v-if="mirror.speed === null && !testingSpeed">未测试</span>
                    <span v-else-if="testingSpeed">测试中...</span>
                    <span v-else-if="mirror.speed === 9999">超时</span>
                    <span v-else>{{ mirror.speed }}ms</span>
                  </div>
                </div>
                <div class="mirror-url">{{ mirror.url }}</div>
              </div>
            </div>
            
            <div class="test-actions">
              <a-button @click="testPythonMirrorSpeed" :loading="testingSpeed" type="primary">
                {{ testingSpeed ? '测速中...' : '重新测速' }}
              </a-button>
              <span class="test-note">3秒无响应视为超时</span>
            </div>
          </div>
          <div v-else class="already-installed">
            <a-result status="success" title="Python 环境已安装" />
          </div>
        </div>

        <!-- 步骤 2: Git 工具 -->
        <div v-if="currentStep === 2" class="step-panel">
          <h3>Git 版本控制工具</h3>
          <div v-if="!gitInstalled" class="install-section">
            <p>需要安装 Git 工具来获取源代码</p>
            <div class="git-info">
              <a-alert 
                message="Git 工具信息" 
                description="将安装便携版 Git 工具，包含完整的版本控制功能，无需系统安装。"
                type="info" 
                show-icon 
              />
            </div>
          </div>
          <div v-else class="already-installed">
            <a-result status="success" title="Git 工具已安装" />
          </div>
        </div>

        <!-- 步骤 3: 源码获取 -->
        <div v-if="currentStep === 3" class="step-panel">
          <h3>获取后端源码</h3>
          <div class="install-section">
            <p>{{ backendExists ? '更新最新的后端代码' : '获取后端源代码' }}</p>
            
            <div class="mirror-grid">
              <div 
                v-for="mirror in gitMirrors" 
                :key="mirror.key"
                class="mirror-card"
                :class="{ active: selectedGitMirror === mirror.key }"
                @click="selectedGitMirror = mirror.key"
              >
                <div class="mirror-header">
                  <h4>{{ mirror.name }}</h4>
                  <div class="speed-badge" :class="getSpeedClass(mirror.speed)">
                    <span v-if="mirror.speed === null && !testingGitSpeed">未测试</span>
                    <span v-else-if="testingGitSpeed">测试中...</span>
                    <span v-else-if="mirror.speed === 9999">超时</span>
                    <span v-else>{{ mirror.speed }}ms</span>
                  </div>
                </div>
                <div class="mirror-url">{{ mirror.url }}</div>
              </div>
            </div>
            
            <div class="test-actions">
              <a-button @click="testGitMirrorSpeed" :loading="testingGitSpeed" type="primary">
                {{ testingGitSpeed ? '测速中...' : '开始测速' }}
              </a-button>
              <span class="test-note">3秒无响应视为超时</span>
            </div>
          </div>
        </div>

        <!-- 步骤 4: 依赖安装 -->
        <div v-if="currentStep === 4" class="step-panel">
          <h3>安装 Python 依赖包</h3>
          <div class="install-section">
            <p>通过 pip 安装项目所需的 Python 依赖包</p>
            
            <div class="mirror-grid">
              <div 
                v-for="mirror in pipMirrors" 
                :key="mirror.key"
                class="mirror-card"
                :class="{ active: selectedPipMirror === mirror.key }"
                @click="selectedPipMirror = mirror.key"
              >
                <div class="mirror-header">
                  <h4>{{ mirror.name }}</h4>
                  <div class="speed-badge" :class="getSpeedClass(mirror.speed)">
                    <span v-if="mirror.speed === null && !testingPipSpeed">未测试</span>
                    <span v-else-if="testingPipSpeed">测试中...</span>
                    <span v-else-if="mirror.speed === 9999">超时</span>
                    <span v-else>{{ mirror.speed }}ms</span>
                  </div>
                </div>
                <div class="mirror-url">{{ mirror.url }}</div>
              </div>
            </div>
            
            <div class="test-actions">
              <a-button @click="testPipMirrorSpeed" :loading="testingPipSpeed" type="primary">
                {{ testingPipSpeed ? '测速中...' : '重新测速' }}
              </a-button>
              <span class="test-note">3秒无响应视为超时</span>
            </div>
          </div>
        </div>

        <!-- 步骤 5: 启动服务 -->
        <div v-if="currentStep === 5" class="step-panel">
          <h3>启动后端服务</h3>
          <div class="service-status">
            <a-spin :spinning="startingService">
              <div class="status-info">
                <p>{{ serviceStatus }}</p>
                <a-progress v-if="showServiceProgress" :percent="serviceProgress" />
              </div>
            </a-spin>
          </div>
        </div>
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
          v-if="currentStep < 5" 
          type="primary" 
          @click="nextStep"
          :loading="isProcessing"
        >
          {{ getNextButtonText() }}
        </a-button>
        
        <a-button 
          v-if="currentStep === 5 && allCompleted" 
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
import { useTheme } from '@/composables/useTheme'
import { createComponentLogger } from '@/utils/logger'
import type { InitializationStatus, DownloadProgress } from '@/types/initialization'
import type { ThemeMode, ThemeColor } from '@/composables/useTheme'

const router = useRouter()
const { themeColors, setThemeMode, setThemeColor } = useTheme()
const logger = createComponentLogger('Initialization')

// 基础状态
const currentStep = ref(0)
const stepStatus = ref<'wait' | 'process' | 'finish' | 'error'>('process')
const errorMessage = ref('')
const isProcessing = ref(false)

// 主题设置
const selectedThemeMode = ref<ThemeMode>('system')
const selectedThemeColor = ref<ThemeColor>('blue')

// 安装状态
const pythonInstalled = ref(false)
const gitInstalled = ref(false)
const backendExists = ref(false)
const dependenciesInstalled = ref(false)

// 镜像源配置
const pythonMirrors = ref([
  { key: 'official', name: 'Python 官方', url: 'https://www.python.org/ftp/python/3.13.0/', speed: null as number | null },
  { key: 'tsinghua', name: '清华 TUNA 镜像', url: 'https://mirrors.tuna.tsinghua.edu.cn/python/3.13.0/', speed: null as number | null },
  { key: 'ustc', name: '中科大镜像', url: 'https://mirrors.ustc.edu.cn/python/3.13.0/', speed: null as number | null },
  { key: 'huawei', name: '华为云镜像', url: 'https://mirrors.huaweicloud.com/repository/toolkit/python/3.13.0/', speed: null as number | null },
  { key: 'aliyun', name: '阿里云镜像', url: 'https://mirrors.aliyun.com/python-release/windows/', speed: null as number | null }
])

const pipMirrors = ref([
  { key: 'official', name: 'PyPI 官方', url: 'https://pypi.org/simple/', speed: null as number | null },
  { key: 'tsinghua', name: '清华大学', url: 'https://pypi.tuna.tsinghua.edu.cn/simple/', speed: null as number | null },
  { key: 'aliyun', name: '阿里云', url: 'https://mirrors.aliyun.com/pypi/simple/', speed: null as number | null },
  { key: 'douban', name: '豆瓣', url: 'https://pypi.douban.com/simple/', speed: null as number | null },
  { key: 'ustc', name: '中科大', url: 'https://pypi.mirrors.ustc.edu.cn/simple/', speed: null as number | null },
  { key: 'huawei', name: '华中科技大学', url: 'https://pypi.hustunique.com/simple/', speed: null as number | null }
])

const gitMirrors = ref([
  { key: 'github', name: 'GitHub 官方', url: 'https://github.com/DLmaster361/AUTO_MAA.git', speed: null as number | null },
  { key: 'fastgit', name: 'FastGit 镜像', url: 'https://ghfast.top/https://github.com/DLmaster361/AUTO_MAA.git', speed: null as number | null }
])

// 选中的镜像源
const selectedPythonMirror = ref('tsinghua')
const selectedPipMirror = ref('tsinghua')
const selectedGitMirror = ref('github')

// 测速状态
const testingSpeed = ref(false)
const testingPipSpeed = ref(false)
const testingGitSpeed = ref(false)

// 服务状态
const startingService = ref(false)
const showServiceProgress = ref(false)
const serviceProgress = ref(0)
const serviceStatus = ref('准备启动后端服务...')

const allCompleted = computed(() => 
  pythonInstalled.value && gitInstalled.value && backendExists.value && dependenciesInstalled.value
)

// 主题设置相关
function onThemeModeChange() {
  setThemeMode(selectedThemeMode.value)
  saveSettings()
}

function onThemeColorChange(color: ThemeColor) {
  selectedThemeColor.value = color
  setThemeColor(color)
  saveSettings()
}

// 保存设置到本地存储
function saveSettings() {
  const settings = {
    themeMode: selectedThemeMode.value,
    themeColor: selectedThemeColor.value,
    pythonMirror: selectedPythonMirror.value,
    pipMirror: selectedPipMirror.value,
    gitMirror: selectedGitMirror.value
  }
  localStorage.setItem('init-settings', JSON.stringify(settings))
}

// 加载设置
function loadSettings() {
  const saved = localStorage.getItem('init-settings')
  if (saved) {
    try {
      const settings = JSON.parse(saved)
      selectedThemeMode.value = settings.themeMode || 'system'
      selectedThemeColor.value = settings.themeColor || 'blue'
      selectedPythonMirror.value = settings.pythonMirror || 'tsinghua'
      selectedPipMirror.value = settings.pipMirror || 'tsinghua'
      selectedGitMirror.value = settings.gitMirror || 'github'
    } catch (error) {
      console.warn('Failed to load settings:', error)
    }
  }
}

// 测速功能 - 带3秒超时
async function testMirrorWithTimeout(url: string, timeout = 3000): Promise<number> {
  const startTime = Date.now()
  
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeout)
    
    await fetch(url, { 
      method: 'HEAD', 
      mode: 'no-cors',
      signal: controller.signal
    })
    
    clearTimeout(timeoutId)
    return Date.now() - startTime
  } catch (error) {
    return 9999 // 超时或失败
  }
}

async function testPythonMirrorSpeed() {
  testingSpeed.value = true
  try {
    // 并发测试所有镜像源
    const promises = pythonMirrors.value.map(async (mirror) => {
      mirror.speed = await testMirrorWithTimeout(mirror.url)
      return mirror
    })
    
    await Promise.all(promises)
    
    // 按速度排序，最快的在前面
    pythonMirrors.value.sort((a, b) => (a.speed || 9999) - (b.speed || 9999))
    
    // 自动选择最快的镜像源
    const fastest = pythonMirrors.value.find(m => m.speed !== 9999)
    if (fastest) {
      selectedPythonMirror.value = fastest.key
    }
  } finally {
    testingSpeed.value = false
  }
}

async function testPipMirrorSpeed() {
  testingPipSpeed.value = true
  try {
    const promises = pipMirrors.value.map(async (mirror) => {
      mirror.speed = await testMirrorWithTimeout(mirror.url)
      return mirror
    })
    
    await Promise.all(promises)
    pipMirrors.value.sort((a, b) => (a.speed || 9999) - (b.speed || 9999))
    
    // 自动选择最快的镜像源
    const fastest = pipMirrors.value.find(m => m.speed !== 9999)
    if (fastest) {
      selectedPipMirror.value = fastest.key
    }
  } finally {
    testingPipSpeed.value = false
  }
}

async function testGitMirrorSpeed() {
  testingGitSpeed.value = true
  try {
    const promises = gitMirrors.value.map(async (mirror) => {
      const url = mirror.url.replace('.git', '')
      mirror.speed = await testMirrorWithTimeout(url)
      return mirror
    })
    
    await Promise.all(promises)
    gitMirrors.value.sort((a, b) => (a.speed || 9999) - (b.speed || 9999))
    
    // 自动选择最快的镜像源
    const fastest = gitMirrors.value.find(m => m.speed !== 9999)
    if (fastest) {
      selectedGitMirror.value = fastest.key
    }
  } finally {
    testingGitSpeed.value = false
  }
}

// 步骤控制
function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

async function nextStep() {
  isProcessing.value = true
  errorMessage.value = ''
  
  try {
    switch (currentStep.value) {
      case 0: // 主题设置
        saveSettings()
        break
      case 1: // Python 环境
        if (!pythonInstalled.value) {
          await installPython()
        }
        break
      case 2: // Git 工具
        if (!gitInstalled.value) {
          await installGit()
        }
        break
      case 3: // 源码获取
        if (!backendExists.value) {
          await cloneBackend()
        } else {
          await updateBackend()
        }
        break
      case 4: // 依赖安装
        if (!dependenciesInstalled.value) {
          await installDependencies()
        }
        break
      case 5: // 启动服务
        await startBackendService()
        break
    }
    
    if (currentStep.value < 5) {
      currentStep.value++
      // 进入新步骤时自动开始测速
      await autoStartSpeedTest()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : String(error)
    stepStatus.value = 'error'
  } finally {
    isProcessing.value = false
  }
}

// 自动开始测速
async function autoStartSpeedTest() {
  switch (currentStep.value) {
    case 1: // Python 环境
      if (!pythonInstalled.value) {
        await testPythonMirrorSpeed()
      }
      break
    case 3: // 源码获取
      await testGitMirrorSpeed()
      break
    case 4: // 依赖安装
      if (!dependenciesInstalled.value) {
        await testPipMirrorSpeed()
      }
      break
  }
}

function getNextButtonText() {
  switch (currentStep.value) {
    case 0: return '下一步'
    case 1: return pythonInstalled.value ? '下一步' : '安装 Python'
    case 2: return gitInstalled.value ? '下一步' : '安装 Git'
    case 3: return backendExists.value ? '更新代码' : '获取代码'
    case 4: return '安装依赖'
    case 5: return '启动服务'
    default: return '下一步'
  }
}

// 检查环境状态
async function checkEnvironment() {
  try {
    logger.info('开始检查环境状态')
    const status = await window.electronAPI.checkEnvironment()
    
    logger.info('环境检查结果', status)
    
    pythonInstalled.value = status.pythonExists
    gitInstalled.value = status.gitExists
    backendExists.value = status.backendExists
    dependenciesInstalled.value = status.dependenciesInstalled
    
    // 如果所有环境都已准备好，跳到最后一步
    if (status.isInitialized) {
      logger.info('环境已初始化完成，跳转到启动服务步骤')
      currentStep.value = 5
      await startBackendService()
    }
  } catch (error) {
    const errorMsg = `环境检查失败: ${error instanceof Error ? error.message : String(error)}`
    logger.error('环境检查失败', error)
    errorMessage.value = errorMsg
  }
}

// 安装 Python
async function installPython() {
  logger.info('开始安装Python', { mirror: selectedPythonMirror.value })
  const result = await window.electronAPI.downloadPython(selectedPythonMirror.value)
  if (result.success) {
    logger.info('Python安装成功')
    pythonInstalled.value = true
  } else {
    logger.error('Python安装失败', result.error)
    throw new Error(result.error)
  }
}

// 安装依赖
async function installDependencies() {
  logger.info('开始安装Python依赖', { mirror: selectedPipMirror.value })
  const result = await window.electronAPI.installDependencies(selectedPipMirror.value)
  if (result.success) {
    logger.info('Python依赖安装成功')
    dependenciesInstalled.value = true
  } else {
    logger.error('Python依赖安装失败', result.error)
    throw new Error(result.error)
  }
}

// 安装 Git
async function installGit() {
  logger.info('开始安装Git工具')
  const result = await window.electronAPI.downloadGit()
  if (result.success) {
    logger.info('Git工具安装成功')
    gitInstalled.value = true
  } else {
    logger.error('Git工具安装失败', result.error)
    throw new Error(result.error)
  }
}

// 克隆后端代码
async function cloneBackend() {
  const selectedMirror = gitMirrors.value.find(m => m.key === selectedGitMirror.value)
  logger.info('开始克隆后端代码', { mirror: selectedMirror?.name, url: selectedMirror?.url })
  const result = await window.electronAPI.cloneBackend(selectedMirror?.url)
  if (result.success) {
    logger.info('后端代码克隆成功')
    backendExists.value = true
  } else {
    logger.error('后端代码克隆失败', result.error)
    throw new Error(result.error)
  }
}

// 更新后端代码
async function updateBackend() {
  const selectedMirror = gitMirrors.value.find(m => m.key === selectedGitMirror.value)
  logger.info('开始更新后端代码', { mirror: selectedMirror?.name, url: selectedMirror?.url })
  const result = await window.electronAPI.updateBackend(selectedMirror?.url)
  if (!result.success) {
    logger.error('后端代码更新失败', result.error)
    throw new Error(result.error)
  }
  logger.info('后端代码更新成功')
}

// 启动后端服务
async function startBackendService() {
  startingService.value = true
  showServiceProgress.value = true
  serviceStatus.value = '正在启动后端服务...'
  
  logger.info('开始启动后端服务')
  
  try {
    const result = await window.electronAPI.startBackend()
    if (result.success) {
      serviceProgress.value = 100
      serviceStatus.value = '后端服务启动成功'
      stepStatus.value = 'finish'
      logger.info('后端服务启动成功')
    } else {
      logger.error('后端服务启动失败', result.error)
      throw new Error(result.error)
    }
  } catch (error) {
    serviceStatus.value = '后端服务启动失败'
    logger.error('后端服务启动异常', error)
    throw error
  } finally {
    startingService.value = false
  }
}

// 进入应用
function enterApp() {
  router.push('/home')
}

// 获取速度样式类
function getSpeedClass(speed: number | null) {
  if (speed === null) return 'speed-unknown'
  if (speed === 9999) return 'speed-timeout'
  if (speed < 500) return 'speed-fast'
  if (speed < 1500) return 'speed-medium'
  return 'speed-slow'
}

// 监听下载进度
function handleDownloadProgress(progress: DownloadProgress) {
  if (progress.type === 'service') {
    serviceProgress.value = progress.progress
    serviceStatus.value = progress.message
  }
}

onMounted(async () => {
  loadSettings()
  await checkEnvironment()
  window.electronAPI.onDownloadProgress(handleDownloadProgress)
  
  // 如果当前步骤需要测速，自动开始测速
  await autoStartSpeedTest()
})

onUnmounted(() => {
  window.electronAPI.removeDownloadProgressListener()
})
</script>

<style scoped>
.initialization-container {
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.initialization-content {
  background: var(--ant-color-bg-container);
  border-radius: 16px;
  padding: 40px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  max-width: 900px;
  width: 100%;
}

.header {
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
  margin: 0;
}

.init-steps {
  margin-bottom: 40px;
}

.step-content {
  min-height: 300px;
  margin-bottom: 40px;
}

.step-panel {
  padding: 20px;
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border);
}

.step-panel h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 20px;
}

.theme-settings {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.setting-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.setting-group label {
  font-weight: 500;
  color: var(--ant-color-text);
}

.color-picker {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.color-option {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s ease;
}

.color-option:hover {
  transform: scale(1.1);
}

.color-option.active {
  border-color: var(--ant-color-text);
  transform: scale(1.1);
}

.install-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.install-section p {
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.mirror-selection {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.mirror-selection label {
  font-weight: 500;
  color: var(--ant-color-text);
  white-space: nowrap;
}

.speed-info {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.already-installed {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.service-status {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 200px;
}

.status-info {
  text-align: center;
  width: 100%;
}

.status-info p {
  font-size: 16px;
  color: var(--ant-color-text);
  margin-bottom: 16px;
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

/* 镜像卡片样式 */
.mirror-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.mirror-card {
  padding: 16px;
  border: 2px solid var(--ant-color-border);
  border-radius: 8px;
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
  margin-bottom: 8px;
}

.mirror-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.speed-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.speed-badge.speed-unknown {
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text-tertiary);
}

.speed-badge.speed-fast {
  background: var(--ant-color-success-bg);
  color: var(--ant-color-success);
}

.speed-badge.speed-medium {
  background: var(--ant-color-warning-bg);
  color: var(--ant-color-warning);
}

.speed-badge.speed-slow {
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
}

.speed-badge.speed-timeout {
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
}

.mirror-url {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  word-break: break-all;
}

.test-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
}

.test-note {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.git-info {
  margin-top: 16px;
}

@media (max-width: 768px) {
  .initialization-content {
    padding: 20px;
    margin: 10px;
  }
  
  .mirror-grid {
    grid-template-columns: 1fr;
  }
  
  .mirror-selection {
    flex-direction: column;
    align-items: stretch;
  }
  
  .mirror-selection label {
    text-align: left;
  }
  
  .step-actions {
    flex-direction: column;
    gap: 12px;
  }
  
  .test-actions {
    flex-direction: column;
    gap: 8px;
  }
}
</style>