<template>
  <div class="auto-mode">
    <div class="header">
      <img src="/src/assets/AUTO_MAA.png" alt="logo" class="logo" />
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
import { createComponentLogger } from '@/utils/logger'
import { getConfig } from '@/utils/config'
import router from '@/router'

const logger = createComponentLogger('AutoMode')

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
  props.onSwitchToManual()
}

// 自动启动流程
async function startAutoProcess() {
  try {
    // 获取配置中保存的镜像源设置
    const config = await getConfig()

    progressText.value = '检查Git仓库更新...'
    progress.value = 20

    // 检查Git仓库是否有更新
    const hasUpdate = await checkGitUpdate()

    if (hasUpdate) {
      progressText.value = '发现更新，正在更新代码...'
      progress.value = 40

      // 使用配置中保存的Git镜像源
      const gitMirrorUrl = getGitMirrorUrl(config.selectedGitMirror)
      const result = await window.electronAPI.updateBackend(gitMirrorUrl)
      if (!result.success) {
        throw new Error(`代码更新失败: ${result.error}`)
      }

      progressText.value = '更新依赖包...'
      progress.value = 60

      // 使用配置中保存的pip镜像源
      const pipResult = await window.electronAPI.installDependencies(config.selectedPipMirror)
      if (!pipResult.success) {
        throw new Error(`依赖更新失败: ${pipResult.error}`)
      }
    }

    progressText.value = '启动后端服务...'
    progress.value = 80
    await startBackendService()

    progressText.value = '启动完成！'
    progress.value = 100
    progressStatus.value = 'success'

    logger.info('自动启动流程完成，即将进入应用')

    // 延迟0.5秒后自动进入应用
    // todo 记得修改这里，为了调试加长了5000s
    setTimeout(() => {
      props.onAutoComplete()
    }, 5000000)
  } catch (error) {
    logger.error('自动启动流程失败', error)
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

// 检查Git更新（简化版本，实际可以调用Git API）
async function checkGitUpdate(): Promise<boolean> {
  // 这里可以实现更复杂的Git更新检查逻辑
  // 暂时返回false，表示没有更新
  return false
}

// 根据镜像源key获取对应的URL
function getGitMirrorUrl(mirrorKey: string): string {
  const mirrors = {
    github: 'https://github.com/DLmaster361/AUTO_MAA.git',
    ghfast: 'https://ghfast.top/https://github.com/DLmaster361/AUTO_MAA.git',
  }
  return mirrors[mirrorKey as keyof typeof mirrors] || mirrors.github
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
