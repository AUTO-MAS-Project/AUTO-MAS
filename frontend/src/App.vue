<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ConfigProvider } from 'ant-design-vue'
import { useTheme } from './composables/useTheme.ts'
import { useUpdateChecker, useUpdateModal } from './composables/useUpdateChecker.ts'
import { useAppClosing } from './composables/useAppClosing.ts'
import AppLayout from './components/AppLayout.vue'
import TitleBar from './components/TitleBar.vue'
import UpdateModal from './components/UpdateModal.vue'
import DevDebugPanel from './components/DevDebugPanel.vue'
import GlobalPowerCountdown from './components/GlobalPowerCountdown.vue'
import WebSocketMessageListener from './components/WebSocketMessageListener.vue'
import AppClosingOverlay from './components/AppClosingOverlay.vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import { logger } from '@/utils/logger'

const route = useRoute()
const { antdTheme, initTheme } = useTheme()
const { updateVisible, updateData, latestVersion, onUpdateConfirmed } = useUpdateModal()
const { startPolling } = useUpdateChecker()
const { isClosing } = useAppClosing()

// 判断是否为初始化页面
const isInitializationPage = computed(() => route.name === 'Initialization')
// 判断是否为 popup 页面（对话框）
const isPopupPage = computed(() => route.name === 'Popup')
// 检查是否为对话框窗口（通过 Electron 参数）
const isDialogWindow = window.electronAPI?.isDialogWindow?.() || false

onMounted(async () => {
  // Popup 页面或对话框窗口跳过所有初始化
  if (isPopupPage.value || isDialogWindow) {
    logger.info('Popup页面或对话框窗口：跳过初始化')
    initTheme() // 只初始化主题
    return
  }

  logger.info('App组件已挂载')
  initTheme()
  logger.info('主题初始化完成')

  // 启动自动更新检查器
  try {
    await startPolling()
    logger.info('自动更新检查器已启动')
  } catch (error) {
    logger.error('启动自动更新检查器失败:', error)
  }
})
</script>

<template>
  <ConfigProvider :theme="antdTheme" :locale="zhCN">
    <!-- Popup 页面或对话框窗口：极简布局，只显示内容 -->
    <div v-if="isPopupPage || isDialogWindow" class="popup-wrapper">
      <router-view />
    </div>
    <!-- 初始化页面使用带标题栏的全屏布局 -->
    <div v-else-if="isInitializationPage" class="initialization-container">
      <TitleBar />
      <div class="initialization-content">
        <router-view />
      </div>
    </div>
    <!-- 其他页面使用带标题栏的应用布局 -->
    <div v-else class="app-container">
      <TitleBar />
      <AppLayout />
    </div>

    <!-- 全局组件（Popup 页面和对话框窗口不加载） -->
    <template v-if="!isPopupPage && !isDialogWindow">
      <!-- 全局更新模态框 -->
      <UpdateModal
        v-model:visible="updateVisible"
        :update-data="updateData"
        :latest-version="latestVersion"
        @confirmed="onUpdateConfirmed"
      />

      <!-- 开发环境调试面板 -->
      <DevDebugPanel />

      <!-- 全局电源倒计时弹窗 -->
      <GlobalPowerCountdown />

      <!-- WebSocket 消息监听组件 -->
      <WebSocketMessageListener />

      <!-- 应用关闭遮罩 -->
      <AppClosingOverlay :visible="isClosing" />
    </template>
  </ConfigProvider>
</template>

<style>
* {
  box-sizing: border-box;
}

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.initialization-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.initialization-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  width: 100%;
  /* 隐藏滚动条但保留滚动功能 */
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE/Edge */
}

/* 隐藏 Webkit 浏览器的滚动条 */
.initialization-content::-webkit-scrollbar {
  display: none;
}

/* Popup 页面极简布局 */
.popup-wrapper {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
}
</style>
