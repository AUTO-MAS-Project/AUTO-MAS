<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ConfigProvider } from 'ant-design-vue'
import { useTheme } from './composables/useTheme.ts'
import AppLayout from './components/AppLayout.vue'
import TitleBar from './components/TitleBar.vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import { logger } from '@/utils/logger'

const route = useRoute()
const { antdTheme, initTheme } = useTheme()

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
  </ConfigProvider>
</template>

<style>
* {
  box-sizing: border-box;
}

.app-container {
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.initialization-container {
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.initialization-content {
  flex: 1;
  overflow: auto;
  width: 100%;
  height: 100%;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
</style>
