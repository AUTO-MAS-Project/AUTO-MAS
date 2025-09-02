<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ConfigProvider } from 'ant-design-vue'
import { useTheme } from './composables/useTheme.ts'
import AppLayout from './components/AppLayout.vue'
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
    <!-- 初始化页面使用全屏布局 -->
    <router-view v-if="isInitializationPage" />
    <!-- 其他页面使用应用布局 -->
    <AppLayout v-else />
  </ConfigProvider>
</template>

<style>
* {
  box-sizing: border-box;
}
</style>
