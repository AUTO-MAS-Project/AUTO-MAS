<template>
  <div class="title-bar" :class="{ 'title-bar-dark': isDark }">
    <!-- 左侧：Logo和软件名 -->
    <div class="title-bar-left">
      <div class="logo-section">
        <!-- 新增虚化主题色圆形阴影 -->
        <span class="logo-glow" aria-hidden="true"></span>
        <img src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="title-logo" />
        <span class="title-text">AUTO-MAS</span>
      </div>
    </div>

    <!-- 中间：可拖拽区域 -->
    <div class="title-bar-center drag-region"></div>

    <!-- 右侧：窗口控制按钮 -->
    <div class="title-bar-right">
      <div class="window-controls">
        <button 
          class="control-button minimize-button" 
          @click="minimizeWindow"
          title="最小化"
        >
          <MinusOutlined />
        </button>
        <button 
          class="control-button maximize-button" 
          @click="toggleMaximize"
          :title="isMaximized ? '还原' : '最大化'"
        >
          <BorderOutlined v-if="!isMaximized" />
          <CopyOutlined v-else />
        </button>
        <button 
          class="control-button close-button" 
          @click="closeWindow"
          title="关闭"
        >
          <CloseOutlined />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { MinusOutlined, BorderOutlined, CopyOutlined, CloseOutlined } from '@ant-design/icons-vue'
import { useTheme } from '@/composables/useTheme'

const { isDark } = useTheme()
const isMaximized = ref(false)

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
    isMaximized.value = await window.electronAPI?.windowIsMaximized() || false
  } catch (error) {
    console.error('Failed to toggle maximize:', error)
  }
}

const closeWindow = async () => {
  try {
    await window.electronAPI?.windowClose()
  } catch (error) {
    console.error('Failed to close window:', error)
  }
}

onMounted(async () => {
  try {
    isMaximized.value = await window.electronAPI?.windowIsMaximized() || false
  } catch (error) {
    console.error('Failed to get window state:', error)
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
  overflow: hidden; /* 新增：裁剪超出顶栏的发光 */
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
  position: relative; /* 使阴影绝对定位基准 */
}

/* 新增：主题色虚化圆形阴影 */
.logo-glow {
  position: absolute;
  left: 55px; /* 调整：更贴近图标 */
  top: 50%;
  transform: translate(-50%, -50%);
  width: 200px;  /* 缩小尺寸以适配 32px 高度 */
  height: 100px;
  pointer-events: none;
  border-radius: 50%;
  background: radial-gradient(circle at 50% 50%, var(--ant-color-primary) 0%, rgba(0,0,0,0) 70%);
  filter: blur(24px); /* 降低模糊避免越界过多 */
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
  z-index: 1; /* 确保在阴影上方 */
}

.title-text {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  position: relative;
  z-index: 1;
}

.title-bar-dark .title-text {
  color: #fff;
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
</style>