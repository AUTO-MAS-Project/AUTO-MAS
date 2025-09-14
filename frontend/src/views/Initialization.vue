<template>
  <div class="initialization-page">
    <!-- 管理员权限检查 -->
    <AdminCheck v-if="!isAdmin" />

    <!-- 环境不完整页面 -->
    <EnvironmentIncomplete
      v-if="showEnvironmentIncomplete"
      :missing-components="missingComponents"
      :on-switch-to-manual="switchToManualMode"
    />

    <!-- 自动初始化模式 -->
    <AutoMode
      v-else-if="autoMode"
      :on-switch-to-manual="switchToManualMode"
      :on-auto-complete="enterApp"
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
import { getConfig, saveConfig, setInitialized } from '@/utils/config'
import AdminCheck from '@/components/initialization/AdminCheck.vue'
import AutoMode from '@/components/initialization/AutoMode.vue'
import ManualMode from '@/components/initialization/ManualMode.vue'
import EnvironmentIncomplete from '@/components/initialization/EnvironmentIncomplete.vue'
import type { DownloadProgress } from '@/types/initialization'
import { mirrorManager } from '@/utils/mirrorManager'

const router = useRouter()

// 基础状态
const isAdmin = ref(true)
const autoMode = ref(false)
const showEnvironmentIncomplete = ref(false)
const missingComponents = ref<string[]>([])

// 安装状态
const pythonInstalled = ref(false)
const gitInstalled = ref(false)
const backendExists = ref(false)
const dependenciesInstalled = ref(false)
const serviceStarted = ref(false)

// 镜像配置状态
const mirrorConfigStatus = ref({
  source: 'fallback' as 'cloud' | 'fallback',
  version: ''
})

// 组件引用
const manualModeRef = ref()

// 基础功能函数
function skipToHome() {
  router.push('/home')
}

function switchToManualMode() {
  showEnvironmentIncomplete.value = false
  autoMode.value = false
  console.log('切换到手动模式')
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
      criticalFiles.pythonExists &&
      criticalFiles.gitExists &&
      criticalFiles.mainPyExists

    console.log('关键exe文件状态检查:')
    console.log('- python.exe存在:', criticalFiles.pythonExists)
    console.log('- git.exe存在:', criticalFiles.gitExists)
    console.log('- main.py存在:', criticalFiles.mainPyExists)
    console.log('- 所有关键文件存在:', allExeFilesExist)

    // 新的自动模式判断逻辑：只要所有关键exe文件都存在且不是第一次启动就进入自动模式
    console.log('自动模式判断条件:')
    console.log('- 不是第一次启动:', !isFirst)
    console.log('- 所有关键文件存在:', allExeFilesExist)

    // 只要不是第一次启动且所有关键exe文件都存在就进入自动模式
    if (!isFirst && allExeFilesExist) {
      console.log('进入自动模式，开始自动启动流程')
      autoMode.value = true
    } else {
      console.log('进入手动模式')
      if (isFirst) {
        console.log('原因: 第一次启动')
        // 第一次启动直接进入手动模式
        autoMode.value = false
        showEnvironmentIncomplete.value = false
      } else if (!allExeFilesExist) {
        console.log('原因: 关键exe文件缺失')
        console.log('  - python.exe缺失:', !criticalFiles.pythonExists)
        console.log('  - git.exe缺失:', !criticalFiles.gitExists)
        console.log('  - main.py缺失:', !criticalFiles.mainPyExists)
        
        // 显示环境不完整页面
        const missing = []
        if (!criticalFiles.pythonExists) missing.push('Python 环境')
        if (!criticalFiles.gitExists) missing.push('Git 工具')
        if (!criticalFiles.mainPyExists) missing.push('后端代码')
        
        missingComponents.value = missing
        showEnvironmentIncomplete.value = true
        autoMode.value = false
      } else {
        // 其他情况直接进入手动模式
        autoMode.value = false
        showEnvironmentIncomplete.value = false
      }
      
      // 如果关键文件缺失，重置初始化状态
      if (!allExeFilesExist && config.init) {
        console.log('检测到关键exe文件缺失，重置初始化状态')
        await saveConfig({ init: false })
      }
    }
  } catch (error) {
    const errorMsg = `环境检查失败: ${error instanceof Error ? error.message : String(error)}`
    console.error('环境检查失败:', error)

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
    version: status.version || ''
  }
  console.log('镜像配置状态:', mirrorConfigStatus.value)

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