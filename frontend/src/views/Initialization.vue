<template>
  <div class="initialization-container">
    <!-- 管理员权限检查 -->
    <AdminCheck v-if="!isAdmin" />

    <!-- 自动初始化模式 -->
    <AutoMode 
      v-if="autoMode"
      :on-switch-to-manual="switchToManualMode"
      :on-auto-complete="enterApp"
    />

    <!-- 手动初始化模式 -->
    <ManualMode 
      v-else
      ref="manualModeRef"
      :python-installed="pythonInstalled"
      :pip-installed="pipInstalled"
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
import { createComponentLogger } from '@/utils/logger'
import { getConfig, saveConfig, setInitialized } from '@/utils/config'
import AdminCheck from '@/components/initialization/AdminCheck.vue'
import AutoMode from '@/components/initialization/AutoMode.vue'
import ManualMode from '@/components/initialization/ManualMode.vue'
import type { DownloadProgress } from '@/types/initialization'

const router = useRouter()
const logger = createComponentLogger('InitializationNew')

// 基础状态
const isAdmin = ref(true)
const autoMode = ref(false)

// 安装状态
const pythonInstalled = ref(false)
const pipInstalled = ref(false)
const gitInstalled = ref(false)
const backendExists = ref(false)
const dependenciesInstalled = ref(false)
const serviceStarted = ref(false)

// 组件引用
const manualModeRef = ref()

// 基础功能函数
function skipToHome() {
  router.push('/home')
}

function switchToManualMode() {
  autoMode.value = false
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
    } else {
      logger.info('首次启动或配置显示未初始化，进入手动模式')
      console.log('进入手动模式')
      console.log('原因: isFirst =', isFirst, ', config.init =', config.init)
    }
  } catch (error) {
    const errorMsg = `环境检查失败: ${error instanceof Error ? error.message : String(error)}`
    logger.error('环境检查失败', error)
    console.error('环境检查失败:', error)
  }
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

// 处理进度更新
function handleProgressUpdate(progress: DownloadProgress) {
  // 这里可以处理全局的进度更新逻辑
  console.log('进度更新:', progress)
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
  
  window.electronAPI.onDownloadProgress(handleProgressUpdate)
  console.log('初始化页面 onMounted 完成')
})

onUnmounted(() => {
  window.electronAPI.removeDownloadProgressListener()
})
</script>

<style scoped>
.initialization-container {
  min-height: 100vh;
  padding: 50px 100px;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .initialization-container {
    padding: 20px;
  }
}
</style>