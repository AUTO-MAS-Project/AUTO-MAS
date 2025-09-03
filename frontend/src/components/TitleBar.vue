<template>
  <div class="title-bar" :class="{ 'title-bar-dark': isDark }">
    <!-- 左侧：Logo和软件名 -->
    <div class="title-bar-left">
      <div class="logo-section">
        <img src="@/assets/AUTO_MAA.ico" alt="AUTO_MAA" class="title-logo" />
        <span class="title-text">AUTO_MAA</span>
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
}

.title-logo {
  width: 20px;
  height: 20px;
}

.title-text {
  font-size: 13px;
  font-weight: 600;
  color: #333;
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