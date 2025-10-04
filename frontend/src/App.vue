<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ConfigProvider } from 'ant-design-vue'
import { useTheme } from './composables/useTheme.ts'
import { useUpdateModal } from './composables/useUpdateChecker.ts'
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
const { updateVisible, updateData, onUpdateConfirmed } = useUpdateModal()
const { isClosing } = useAppClosing()

// 判断是否为初始化页面
const isInitializationPage = computed(() => route.name === 'Initialization')

onMounted(() => {
  logger.info('App组件已挂载')
  initTheme()
  logger.info('主题初始化完成')
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
    <!-- 其他页面使用带标题栏的应用布局 -->
    <div v-else class="app-container">
      <TitleBar />
      <AppLayout />
    </div>

    <!-- 全局更新模态框 -->
    <UpdateModal
      v-model:visible="updateVisible"
      :update-data="updateData"
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
</style>
