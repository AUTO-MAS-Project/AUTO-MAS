<template>
  <div class="auto-mode">
    <div class="header">
      <img src="/src/assets/AUTO-MAS.ico" alt="logo" class="logo" />
      <a-typography-title :level="1">AUTO_MAA</a-typography-title>
    </div>
    <div class="tip">
      <a-typography-title :level="3">检测到环境已配置，正在启动后端~~</a-typography-title>
    </div>

    <div class="auto-progress">
      <a-spin size="large" />
      <div class="progress-text">{{ progressText }}</div>
      <a-progress :percent="progress" :status="progressStatus" />
    </div>

    <div class="auto-actions">
      <a-button @click="handleSwitchToManual" type="primary" size="large">重新配置环境</a-button>
      <a-button @click="handleForceEnter" type="default" size="large">强行进入应用</a-button>
    </div>
  </div>

  <!-- 弹窗 -->
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
import { ref, onMounted } from 'vue'
import { getConfig } from '@/utils/config'
import { getMirrorUrl } from '@/config/mirrors'
import router from '@/router'



// Props
interface Props {
  onSwitchToManual: () => void
  onAutoComplete: () => void
}

const props = defineProps<Props>()

// 状态
const progress = ref(0)
const progressText = ref('')
const progressStatus = ref<'normal' | 'exception' | 'success'>('normal')

// 状态：控制是否取消自动启动
const aborted = ref(false)

// 状态：控制弹窗显隐
const forceEnterVisible = ref(false)

// 点击“强行进入应用”按钮，显示弹窗
function handleForceEnter() {
  forceEnterVisible.value = true
}

// 确认弹窗中的“我知道我在做什么”按钮，直接进入应用
function handleForceEnterConfirm() {
  forceEnterVisible.value = false
  router.push('/home')
}

// 事件处理
function handleSwitchToManual() {
  aborted.value = true // 设置中断
  props.onSwitchToManual()
}

// 自动启动流程
async function startAutoProcess() {
  try {
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

      // 使用配置中保存的Git镜像源
      const gitMirrorUrl = getGitMirrorUrl(config.selectedGitMirror)
      const result = await window.electronAPI.updateBackend(gitMirrorUrl)
      if (aborted.value) return
      if (!result.success) {
        throw new Error(`代码更新失败: ${result.error}`)
      }
    }

    // 无论是否有更新，都检查并安装依赖
    progressText.value = '检查并安装依赖包...'
    progress.value = 60

    // 先尝试使用初始化时的镜像源
    let pipMirror = config.selectedPipMirror || 'tsinghua'
    let pipResult = await window.electronAPI.installDependencies(pipMirror)
    if (aborted.value) return

    // 如果初始化时的镜像源不通，让用户重新选择
    if (!pipResult.success) {
      console.warn(`使用镜像源 ${pipMirror} 安装依赖失败，需要重新选择镜像源`)

      // 切换到手动模式让用户重新选择镜像源
      progressText.value = '依赖安装失败，需要重新配置镜像源'
      progressStatus.value = 'exception'

      setTimeout(() => {
        progressText.value = '请点击下方按钮重新配置环境'
      }, 2000)

      return
    }

    progressText.value = '启动后端服务...'
    progress.value = 80
    await startBackendService()
    if (aborted.value) return

    progressText.value = '启动完成！'
    progress.value = 100
    progressStatus.value = 'success'

    console.log('自动启动流程完成，即将进入应用')

    // 延迟0.5秒后自动进入应用
    setTimeout(() => {
      props.onAutoComplete()
    }, 500)
  } catch (error) {
    console.error('自动启动流程失败', error)
    progressText.value = `自动启动失败: ${error instanceof Error ? error.message : String(error)}`
    progressStatus.value = 'exception'

    // 5秒后提供切换到手动模式的选项
    setTimeout(() => {
      if (progressStatus.value === 'exception') {
        progressText.value = '自动启动失败，请点击下方按钮重新配置环境'
      }
    }, 5000)
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

// 根据镜像源key获取对应的URL
function getGitMirrorUrl(mirrorKey: string): string {
  return getMirrorUrl('git', mirrorKey)
}

// 启动后端服务
async function startBackendService() {
  const result = await window.electronAPI.startBackend()
  if (!result.success) {
    throw new Error(`后端服务启动失败: ${result.error}`)
  }
}

// 组件挂载时开始自动流程
onMounted(() => {
  aborted.value = false
  startAutoProcess()
})
</script>

<style scoped>
.auto-mode {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}

.header {
  text-align: center;
  margin-bottom: 40px;
  margin-top: 100px;
  flex: auto;
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
  display: flex;
  gap: 20px;
}
</style>
