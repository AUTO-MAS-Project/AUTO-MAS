<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ConfigProvider } from 'ant-design-vue'
import { useTheme } from './composables/useTheme.ts'
import { useUpdateModal } from './composables/useUpdateChecker.ts'
import { useAppClosing } from './composables/useAppClosing.ts'
import { useAudioPlayer } from './composables/useAudioPlayer.ts'
import { useAppInitialization } from './composables/useAppInitialization.ts'
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
const { isClosing } = useAppClosing()
const { playSound } = useAudioPlayer()
const { isInitialized } = useAppInitialization()

// 判断是否为初始化页面
const isInitializationPage = computed(() => route.name === 'Initialization')

onMounted(async () => {
  logger.info('App组件已挂载')
  initTheme()
  logger.info('主题初始化完成')
  logger.info('初始化状态:', {
    isInitializationPage: isInitializationPage.value,
    isInitialized: isInitialized.value
  })

  // 注意：版本检查服务已在 appEntry.ts 中统一启动，此处不再重复启动

  // 播放欢迎音频（非初始化页面且已初始化时）
  if (!isInitializationPage.value && isInitialized.value) {
    logger.info('准备播放欢迎音频')
    await playSound('welcome_back')
  } else {
    logger.info('跳过欢迎音频播放', {
      reason: isInitializationPage.value ? '当前是初始化页面' : '应用未初始化'
    })
  }
})
</script>

<template>
  <ConfigProvider :theme="antdTheme" :locale="zhCN">
    <!-- 初始化页面使用带标题栏的全屏布局 -->
    <div v-if="isInitializationPage" class="initialization-container">
      <TitleBar />
      <div class="initialization-content">
        <router-view />
      </div>
    </div>
    <!-- 其他页面使用带标题栏的应用布局 - 仅在初始化完成后挂载 -->
    <div v-else-if="isInitialized" class="app-container">
      <TitleBar />
      <AppLayout />
    </div>

    <!-- 开发环境调试面板 - 开发工具始终可用 -->
    <DevDebugPanel />

    <!-- 以下组件仅在初始化完成后挂载 -->
    <template v-if="isInitialized">
      <!-- 全局更新模态框 -->
      <UpdateModal v-model:visible="updateVisible" :update-data="updateData" :latest-version="latestVersion"
        @confirmed="onUpdateConfirmed" />

      <!-- 全局电源倒计时弹窗 -->
      <GlobalPowerCountdown />

      <!-- WebSocket 消息监听组件 -->
      <WebSocketMessageListener />
    </template>

    <!-- 应用关闭遮罩 - 始终可用 -->
    <AppClosingOverlay :visible="isClosing" />
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
  scrollbar-width: none;
  /* Firefox */
  -ms-overflow-style: none;
  /* IE/Edge */
}

/* 隐藏 Webkit 浏览器的滚动条 */
.initialization-content::-webkit-scrollbar {
  display: none;
}
</style>
