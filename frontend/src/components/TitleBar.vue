<template>
  <div class="title-bar" :class="{ 'title-bar-dark': isDark }">
    <!-- 左侧：Logo和软件名 -->
    <div class="title-bar-left">
      <div class="logo-section">
        <!-- 新增虚化主题色圆形阴影 -->
        <span class="logo-glow" aria-hidden="true"></span>
        <img src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="title-logo" />
        <span class="title-text">AUTO-MAS</span>
        <span class="version-text">
          v{{ version }}
          <span v-if="updateInfo?.if_need_update" class="update-hint" :title="getUpdateTooltip()">
            检测到更新 {{ updateInfo.latest_version }} 请尽快更新
          </span>
          <span v-if="backendUpdateInfo?.if_need_update" class="update-hint" :title="getUpdateTooltip()">
            检测到更新后端有更新。请重启软件即可自动完成更新
          </span>
        </span>
      </div>
    </div>

    <!-- 中间：可拖拽区域 -->
    <div class="title-bar-center drag-region"></div>

    <!-- 右侧：窗口控制按钮 -->
    <div class="title-bar-right">
      <div class="window-controls">
        <button class="control-button minimize-button" @click="minimizeWindow" title="最小化">
          <MinusOutlined />
        </button>
        <button class="control-button maximize-button" @click="toggleMaximize" :title="isMaximized ? '还原' : '最大化'">
          <BorderOutlined />
        </button>
        <button class="control-button close-button" @click="closeWindow" title="关闭">
          <CloseOutlined />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { BorderOutlined, CloseOutlined, CopyOutlined, MinusOutlined } from '@ant-design/icons-vue'
import { useTheme } from '@/composables/useTheme'
import type { UpdateCheckOut } from '@/api'
import { Service, type VersionOut } from '@/api'

const { isDark } = useTheme()
const isMaximized = ref(false)

// 使用 import.meta.env 或直接定义版本号，确保打包后可用
const version = import.meta.env.VITE_APP_VERSION || '获取版本失败！'
const updateInfo = ref<UpdateCheckOut | null>(null)
const backendUpdateInfo = ref<VersionOut | null>(null)

const POLL_MS = 10 * 60 * 1000 // 10 分钟
let pollTimer: number | null = null
const polling = ref(false)

// 获取是否有更新
const getAppVersion = async () => {
  try {
    const ver = await Service.checkUpdateApiUpdateCheckPost({
      current_version: version,
    })
    updateInfo.value = ver
    return ver || '获取版本失败！'
  } catch (error) {
    console.error('Failed to get app version:', error)
    return '获取前端版本失败！'
  }
}

const getBackendVersion = async () => {
  try {
    backendUpdateInfo.value = await Service.getGitVersionApiInfoVersionPost()
  } catch (error) {
    console.error('Failed to get backend version:', error)
    return '获取后端版本失败！'
  }
}

// 生成更新提示的详细信息
const getUpdateTooltip = () => {
  if (!updateInfo.value?.update_info) return ''

  const updateDetails = []
  for (const [category, items] of Object.entries(updateInfo.value.update_info)) {
    if (items && items.length > 0) {
      updateDetails.push(`${category}:`)
      items.forEach(item => {
        updateDetails.push(`• ${item}`)
      })
      updateDetails.push('')
    }
  }
  return updateDetails.join('\n')
}

const minimizeWindow = async () => {
  try {
    await window.electronAPI?.windowMinimize()
  } catch (error) {
    console.error('Failed to minimize window:', error)
  }
}

const toggleMaximize = async () => {
  try {
    await window.electronAPI?.windowMaximize()
    isMaximized.value = (await window.electronAPI?.windowIsMaximized()) || false
  } catch (error) {
    console.error('Failed to toggle maximize:', error)
  }
}

const closeWindow = async () => {
  try {
    console.log('开始关闭应用...')

    // 先检查当前进程状态
    try {
      const processes = await window.electronAPI?.getRelatedProcesses()
      console.log('关闭前的进程状态:', processes)
    } catch (e) {
      console.warn('无法获取进程状态:', e)
    }

    // 异步调用后端关闭API，不等待响应
    Service.closeApiCoreClosePost().catch(error => {
      console.warn('Backend close API failed (this is expected):', error)
    })

    // 使用更激进的强制退出方法
    try {
      console.log('执行强制退出...')
      await window.electronAPI?.forceExit()
    } catch (error) {
      console.error('强制退出失败，尝试备用方法:', error)

      // 备用方法：先尝试正常关闭
      try {
        await window.electronAPI?.windowClose()
        setTimeout(async () => {
          await window.electronAPI?.appQuit()
        }, 500)
      } catch (backupError) {
        console.error('备用方法也失败:', backupError)
      }
    }
  } catch (error) {
    console.error('关闭应用失败:', error)
  }
}

const pollOnce = async () => {
  if (polling.value) return
  polling.value = true
  try {
    const [appRes, backendRes] = await Promise.allSettled([getAppVersion(), getBackendVersion()])

    if (appRes.status === 'rejected') {
      console.error('getAppVersion failed:', appRes.reason)
    }
    if (backendRes.status === 'rejected') {
      console.error('getBackendVersion failed:', backendRes.reason)
    }
  } finally {
    polling.value = false
  }
}

onMounted(async () => {
  try {
    isMaximized.value = (await window.electronAPI?.windowIsMaximized()) || false
  } catch (error) {
    console.error('Failed to get window state:', error)
  }
  // 初始化立即跑一次
  await pollOnce()
  // 每 10 分钟检查一次更新
  pollTimer = window.setInterval(pollOnce, POLL_MS)
})

onBeforeUnmount(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<style scoped>
.title-bar {
  height: 32px;
  background: #ffffff;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
  position: relative;
  z-index: 1000;
  overflow: hidden;
  /* 新增：裁剪超出顶栏的发光 */
}

.title-bar-dark {
  background: #1f1f1f;
  border-bottom: 1px solid #333;
}

.title-bar-left {
  display: flex;
  align-items: center;
  padding-left: 12px;
  height: 100%;
}

.logo-section {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
  /* 使阴影绝对定位基准 */
}

/* 新增：主题色虚化圆形阴影 */
.logo-glow {
  position: absolute;
  left: 55px;
  /* 调整：更贴近图标 */
  top: 50%;
  transform: translate(-50%, -50%);
  width: 200px;
  /* 缩小尺寸以适配 32px 高度 */
  height: 100px;
  pointer-events: none;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 50%, var(--ant-color-primary) 0%, rgba(0, 0, 0, 0) 70%);
  filter: blur(24px);
  /* 降低模糊避免越界过多 */
  opacity: 0.4;
  z-index: 0;
}

.title-bar-dark .logo-glow {
  opacity: 0.7;
  filter: blur(24px);
}

.title-logo {
  width: 20px;
  height: 20px;
  position: relative;
  z-index: 1;
  /* 确保在阴影上方 */
}

.title-text {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  position: relative;
  z-index: 1;
}

.version-text {
  font-size: 13px;
  font-weight: 400;
  opacity: 0.8;
  position: relative;
  z-index: 1;
  margin-left: 4px;
}

.title-bar-dark .title-text {
  color: #fff;
}

.title-bar-dark .version-text {
  color: #ffffff;
}

.title-bar-center {
  flex: 1;
  height: 100%;
}

.drag-region {
  -webkit-app-region: drag;
}

.title-bar-right {
  display: flex;
  align-items: center;
  height: 100%;
}

.window-controls {
  display: flex;
  height: 100%;
}

.control-button {
  width: 46px;
  height: 32px;
  border: none;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 0.2s;
  color: #666;
  font-size: 12px;
  -webkit-app-region: no-drag;
}

.title-bar-dark .control-button {
  color: #ccc;
}

.control-button:hover {
  background: rgba(0, 0, 0, 0.05);
}

.title-bar-dark .control-button:hover {
  background: rgba(255, 255, 255, 0.1);
}

.close-button:hover {
  background: #e81123 !important;
  color: #fff !important;
}

.minimize-button:hover,
.maximize-button:hover {
  background: rgba(0, 0, 0, 0.08);
}

.title-bar-dark .minimize-button:hover,
.title-bar-dark .maximize-button:hover {
  background: rgba(255, 255, 255, 0.15);
}

.update-hint {
  font-weight: 600;
  margin-left: 4px;
  cursor: help;
  background: linear-gradient(45deg, #ff1744, #ff5722, #ff9800, #ffc107, #4caf50, #00bcd4, #2196f3, #9c27b0, #ff1744);
  background-size: 400% 400%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation:
    rainbow-flow 3s ease-in-out infinite,
    glow-pulse 2s ease-in-out infinite;
  position: relative;
  filter: drop-shadow(0 0 4px rgba(255, 64, 129, 0.4));
  transition: all 0.3s ease;
  font-size: 13px;
  line-height: 1.2;
  padding: 2px 4px;
  border-radius: 4px;
}

.update-hint:hover {
  transform: scale(1.02);
  filter: drop-shadow(0 0 8px rgba(255, 64, 129, 0.7));
  animation-duration: 3s, 2s;
}

.update-hint::before {
  content: '';
  position: absolute;
  top: -2px;
  left: -2px;
  right: -2px;
  bottom: -2px;
  background: linear-gradient(45deg, #ff1744, #ff5722, #ff9800, #ffc107, #4caf50, #00bcd4, #2196f3, #9c27b0, #ff1744);
  background-size: 400% 400%;
  border-radius: 6px;
  z-index: -1;
  opacity: 0.12;
  filter: blur(8px);
  animation: rainbow-flow 4s ease-in-out infinite;
}

.update-hint::after {
  content: '';
  position: absolute;
  top: -3px;
  left: -3px;
  right: -3px;
  bottom: -3px;
  background: radial-gradient(circle at center, rgba(255, 64, 129, 0.08) 0%, transparent 70%);
  border-radius: 8px;
  z-index: -2;
  animation: pulse-ring 4s ease-in-out infinite;
}

/* 为相邻的更新提示添加间距 */
.update-hint+.update-hint {
  margin-left: 12px;
}

.title-bar-dark .update-hint {
  filter: drop-shadow(0 0 6px rgba(255, 64, 129, 0.6));
}

.title-bar-dark .update-hint::before {
  opacity: 0.2;
  filter: blur(10px);
}

.title-bar-dark .update-hint::after {
  background: radial-gradient(circle at center, rgba(255, 64, 129, 0.15) 0%, transparent 70%);
}

@keyframes rainbow-flow {
  0% {
    background-position: 0% 50%;
  }

  50% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0% 50%;
  }
}

@keyframes glow-pulse {
  0% {
    filter: drop-shadow(0 0 4px rgba(255, 64, 129, 0.4)) brightness(1);
    transform: scale(1);
  }

  33% {
    filter: drop-shadow(0 0 6px rgba(255, 152, 0, 0.5)) brightness(1.08);
    transform: scale(1.003);
  }

  66% {
    filter: drop-shadow(0 0 5px rgba(76, 175, 80, 0.45)) brightness(1.05);
    transform: scale(1.002);
  }

  100% {
    filter: drop-shadow(0 0 4px rgba(255, 64, 129, 0.4)) brightness(1);
    transform: scale(1);
  }
}

@keyframes pulse-ring {
  0% {
    opacity: 0.08;
    transform: scale(0.98);
  }

  50% {
    opacity: 0.04;
    transform: scale(1.02);
  }

  100% {
    opacity: 0.08;
    transform: scale(0.98);
  }
}
</style>
