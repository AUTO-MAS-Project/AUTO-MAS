<template>
  <div class="initialization-page">
    <!-- 管理员权限检查 -->
    <AdminCheck v-if="!isAdmin" />

    <!-- 安装模式选择 -->
    <InstallModeSelection v-if="showModeSelection" :on-mode-selected="handleModeSelected" />

    <!-- 环境不完整页面 -->
    <EnvironmentIncomplete
      v-else-if="showEnvironmentIncomplete"
      :missing-components="missingComponents"
      :on-switch-to-manual="switchToManualMode"
    />

    <!-- 自动初始化模式 -->
    <AutoMode
      v-else-if="autoMode"
      :on-switch-to-manual="switchToManualMode"
      :on-auto-complete="enterApp"
    />

    <!-- 快速安装模式 -->
    <QuickInstallMode
      v-else-if="quickInstallMode"
      :on-switch-to-manual="switchToManualMode"
      :on-quick-complete="enterApp"
    />

    <!-- 手动初始化模式 -->
    <ManualMode
      v-else
      ref="manualModeRef"
      :python-installed="pythonInstalled"
      :git-installed="gitInstalled"
      :backend-exists="backendExists"
      :dependencies-installed="dependenciesInstalled"
      :service-started="serviceStarted"
      :on-skip-to-home="skipToHome"
      :on-enter-app="enterApp"
      :on-progress-update="handleProgressUpdate"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getConfig, saveConfig, setInitialized } from '@/utils/config.ts'
import AdminCheck from '@/views/Initialization/components/AdminCheck.vue'
import AutoMode from '@/views/Initialization/components/AutoMode.vue'
import ManualMode from '@/views/Initialization/components/ManualMode.vue'
import EnvironmentIncomplete from '@/views/Initialization/components/EnvironmentIncomplete.vue'
import InstallModeSelection from '@/views/Initialization/components/InstallModeSelection.vue'
import QuickInstallMode from '@/views/Initialization/components/QuickInstallMode.vue'
import type { DownloadProgress } from '@/types/initialization.ts'
import { mirrorManager } from '@/utils/mirrorManager.ts'
import { forceEnterApp } from '@/utils/appEntry.ts'

const router = useRouter()

// 基础状态
const isAdmin = ref(true)
const autoMode = ref(false)
const showEnvironmentIncomplete = ref(false)
const missingComponents = ref<string[]>([])
const showModeSelection = ref(false)
const quickInstallMode = ref(false)

// 安装状态
const pythonInstalled = ref(false)
const gitInstalled = ref(false)
const backendExists = ref(false)
const dependenciesInstalled = ref(false)
const serviceStarted = ref(false)

// 镜像配置状态
const mirrorConfigStatus = ref({
  source: 'fallback' as 'cloud' | 'fallback',
  version: '',
})

// 组件引用
const manualModeRef = ref()

// 基础功能函数
async function skipToHome() {
  await forceEnterApp('跳过初始化直接进入')
}

function switchToManualMode() {
  showEnvironmentIncomplete.value = false
  autoMode.value = false
  quickInstallMode.value = false
  showModeSelection.value = true
  console.log('切换到安装模式选择')
}

// 处理安装模式选择
function handleModeSelected(mode: 'quick' | 'manual') {
  showModeSelection.value = false
  if (mode === 'quick') {
    quickInstallMode.value = true
    autoMode.value = false
  } else {
    quickInstallMode.value = false
    autoMode.value = false
  }
  console.log('选择安装模式:', mode)
}

// 进入应用
async function enterApp() {
  try {
    // 设置初始化完成标记
    await setInitialized(true)
    console.log('设置初始化完成标记，准备进入应用...')

    // 使用统一的进入应用函数
    await forceEnterApp('初始化完成后进入')
  } catch (error) {
    console.error('进入应用失败:', error)
    // 即使出错也强制进入
    await forceEnterApp('初始化失败后强制进入')
  }
}

// 检查关键文件是否存在
async function checkCriticalFiles() {
  try {
    console.log('🔍 正在调用 window.electronAPI.checkCriticalFiles()...')

    // 检查API是否存在
    if (!window.electronAPI.checkCriticalFiles) {
      console.warn('⚠️ window.electronAPI.checkCriticalFiles 不存在，使用配置文件状态')
      // 如果API不存在，从配置文件读取状态
      const config = await getConfig()
      return {
        pythonExists: config.pythonInstalled || false,
        gitExists: config.gitInstalled || false,
        mainPyExists: config.backendExists || false,
      }
    }

    // 检查关键文件
    const criticalFiles = await window.electronAPI.checkCriticalFiles()

    console.log('🔍 electronAPI.checkCriticalFiles() 原始返回结果:', criticalFiles)
    console.log('🔍 详细检查结果:')
    console.log('  - pythonExists:', criticalFiles.pythonExists, typeof criticalFiles.pythonExists)
    console.log('  - gitExists:', criticalFiles.gitExists, typeof criticalFiles.gitExists)
    console.log('  - mainPyExists:', criticalFiles.mainPyExists, typeof criticalFiles.mainPyExists)

    const result = {
      pythonExists: criticalFiles.pythonExists,
      gitExists: criticalFiles.gitExists,
      mainPyExists: criticalFiles.mainPyExists,
    }

    console.log('🔍 最终返回结果:', result)
    return result
  } catch (error) {
    console.error('❌ 检查关键文件失败，使用配置文件状态:', error)

    // 如果检查失败，从配置文件读取状态
    try {
      const config = await getConfig()
      console.log('📄 使用配置文件中的状态:', {
        pythonInstalled: config.pythonInstalled,
        gitInstalled: config.gitInstalled,
        backendExists: config.backendExists,
      })
      return {
        pythonExists: config.pythonInstalled || false,
        gitExists: config.gitInstalled || false,
        mainPyExists: config.backendExists || false,
      }
    } catch (configError) {
      console.error('❌ 读取配置文件也失败了:', configError)
      return {
        pythonExists: false,
        gitExists: false,
        mainPyExists: false,
      }
    }
  }
}

// 检查环境状态
async function checkEnvironment() {
  try {
    // 每次都重新检查关键exe文件是否存在，不依赖持久化配置
    const criticalFiles = await checkCriticalFiles()

    console.log('关键文件检查结果:', criticalFiles)

    // 直接根据exe文件存在性设置状态
    pythonInstalled.value = criticalFiles.pythonExists
    gitInstalled.value = criticalFiles.gitExists
    backendExists.value = criticalFiles.mainPyExists

    // 依赖安装状态从配置文件读取，但在手动模式中会重新安装
    const config = await getConfig()
    dependenciesInstalled.value = config.dependenciesInstalled || false

    console.log('📊 最终状态设置:')
    console.log('  - pythonInstalled:', pythonInstalled.value)
    console.log('  - gitInstalled:', gitInstalled.value)
    console.log('  - backendExists:', backendExists.value)
    console.log('  - dependenciesInstalled:', dependenciesInstalled.value)

    // 检查是否第一次启动
    const isFirst = config.isFirstLaunch
    console.log('是否第一次启动:', isFirst)

    // 检查所有关键exe文件是否都存在
    const allExeFilesExist =
      criticalFiles.pythonExists && criticalFiles.gitExists && criticalFiles.mainPyExists

    console.log('关键exe文件状态检查:')
    console.log('- python.exe存在:', criticalFiles.pythonExists)
    console.log('- git.exe存在:', criticalFiles.gitExists)
    console.log('- main.py存在:', criticalFiles.mainPyExists)
    console.log('- 所有关键文件存在:', allExeFilesExist)

    // 🆕 智能初始化逻辑：
    // 1. 如果所有关键文件都存在（Full版本或已安装过）
    //    - 直接进入自动模式（会自动检查更新、安装依赖并启动）
    // 2. 如果关键文件部分或全部缺失
    //    - 第一次启动 → 安装模式选择
    //    - 非第一次启动 → 环境不完整页面

    console.log('🎯 智能初始化判断:')
    console.log('- 第一次启动:', isFirst)
    console.log('- 所有关键文件存在:', allExeFilesExist)
    console.log('- 依赖已安装:', dependenciesInstalled.value)

    if (allExeFilesExist) {
      // 环境完整（Full 版本或已安装过）
      console.log('✅ 检测到完整环境，进入自动模式')

      // 如果是第一次启动且环境完整，说明是 Full 版本
      if (isFirst) {
        console.log('🎉 检测到预装环境（Full版本），自动配置初始化状态')
        // 更新配置，标记不再是第一次启动
        await saveConfig({
          isFirstLaunch: false,
          pythonInstalled: true,
          gitInstalled: true,
          backendExists: true,
        })
      }

      // 直接进入自动模式，会自动检查并安装缺失的依赖
      autoMode.value = true
      showEnvironmentIncomplete.value = false
      showModeSelection.value = false
      quickInstallMode.value = false
    } else {
      // 环境不完整
      if (isFirst) {
        // 第一次启动且环境不完整 → 安装模式选择（Lite版本）
        console.log('📋 第一次启动且环境不完整（Lite版本），显示安装模式选择')
        showModeSelection.value = true
        autoMode.value = false
        quickInstallMode.value = false
        showEnvironmentIncomplete.value = false
      } else {
        // 非第一次启动但环境损坏 → 环境不完整页面
        console.log('⚠️ 环境损坏，显示环境不完整页面')

        const missing = []
        if (!criticalFiles.pythonExists) missing.push('Python 环境')
        if (!criticalFiles.gitExists) missing.push('Git 工具')
        if (!criticalFiles.mainPyExists) missing.push('后端代码')

        missingComponents.value = missing
        showEnvironmentIncomplete.value = true
        autoMode.value = false
        showModeSelection.value = false
        quickInstallMode.value = false

        // 重置初始化状态
        console.log('重置初始化状态')
        await saveConfig({ init: false })
      }
    }
  } catch (error) {
    const errorMsg = `环境检查失败: ${error instanceof Error ? error.message : String(error)}`
    console.error(errorMsg)

    // 检查失败时强制进入手动模式
    autoMode.value = false
  }
}

// 检查管理员权限
async function checkAdminPermission() {
  try {
    const adminStatus = await window.electronAPI.checkAdmin()
    isAdmin.value = adminStatus
    console.log('管理员权限检查结果:', adminStatus)
  } catch (error) {
    console.error('检查管理员权限失败:', error)
    isAdmin.value = false
  }
}

// 处理进度更新
function handleProgressUpdate(progress: DownloadProgress) {
  // 这里可以处理全局的进度更新逻辑
  console.log('进度更新:', progress)
}

onMounted(async () => {
  console.log('初始化页面 onMounted 开始')

  // 更新镜像配置状态
  const status = mirrorManager.getConfigStatus()
  mirrorConfigStatus.value = {
    source: status.source,
    version: status.version || '',
  }
  console.log('镜像配置状态:', mirrorConfigStatus.value)

  // 测试配置系统
  try {
    console.log('测试配置系统...')
    const testConfig = await getConfig()
    console.log('当前配置:', testConfig)
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

  window.electronAPI.onDownloadProgress(handleProgressUpdate)
  console.log('初始化页面 onMounted 完成')
})

onUnmounted(() => {
  window.electronAPI.removeDownloadProgressListener()
})
</script>

<style scoped>
.initialization-page {
  padding: 20px;
  box-sizing: border-box;
  width: 100%;
  min-height: 100%;
  background-color: var(--ant-color-bg-layout);
  color: var(--ant-color-text);
}

/* 响应式优化 */
@media (max-width: 768px) {
  .initialization-page {
    padding: 10px;
  }
}
</style>
