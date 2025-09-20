<template>
  <div class="environment-page">
    <!-- 环境信息 -->
    <div class="debug-section">
      <h4>⚙️ 环境信息</h4>
      <div class="info-item">
        <span class="label">Vue版本:</span>
        <span class="value">{{ vueVersion }}</span>
      </div>
      <div class="info-item">
        <span class="label">开发模式:</span>
        <span class="value">{{ isDev ? '是' : '否' }}</span>
      </div>
      <div class="info-item">
        <span class="label">当前时间:</span>
        <span class="value">{{ currentTime }}</span>
      </div>
      <div class="info-item">
        <span class="label">用户代理:</span>
        <span class="value">{{ userAgent }}</span>
      </div>
      <div class="info-item">
        <span class="label">屏幕分辨率:</span>
        <span class="value">{{ screenResolution }}</span>
      </div>
      <div class="info-item">
        <span class="label">窗口尺寸:</span>
        <span class="value">{{ windowSize }}</span>
      </div>
    </div>

    <!-- 性能信息 -->
    <div class="debug-section">
      <h4>📊 性能信息</h4>
      <div class="info-item">
        <span class="label">内存使用:</span>
        <span class="value">{{ memoryInfo }}</span>
      </div>
      <div class="info-item">
        <span class="label">页面加载时间:</span>
        <span class="value">{{ loadTime }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, version } from 'vue'

// Vue版本
const vueVersion = ref(version)

// 开发环境检测
const isDev = ref(process.env.NODE_ENV === 'development' || import.meta.env?.DEV === true)

// 当前时间
const currentTime = ref('')

// 环境信息
const userAgent = ref('')
const screenResolution = ref('')
const windowSize = ref('')
const memoryInfo = ref('')
const loadTime = ref('')

// 更新时间
const updateTime = () => {
  currentTime.value = new Date().toLocaleString()
}

// 更新窗口尺寸
const updateWindowSize = () => {
  windowSize.value = `${window.innerWidth}x${window.innerHeight}`
}

// 获取内存信息
const updateMemoryInfo = () => {
  if ('memory' in performance) {
    const memory = (performance as any).memory
    const used = Math.round(memory.usedJSHeapSize / 1024 / 1024)
    const total = Math.round(memory.totalJSHeapSize / 1024 / 1024)
    const limit = Math.round(memory.jsHeapSizeLimit / 1024 / 1024)
    memoryInfo.value = `${used}MB / ${total}MB (限制: ${limit}MB)`
  } else {
    memoryInfo.value = '不支持'
  }
}

// 获取页面加载时间
const getLoadTime = () => {
  if ('performance' in window) {
    const perfData = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
    if (perfData) {
      const loadTime = Math.round(perfData.loadEventEnd - perfData.navigationStart)
      return `${loadTime}ms`
    }
  }
  return '未知'
}

// 定时器
let timeInterval: NodeJS.Timeout

onMounted(() => {
  // 初始化环境信息
  userAgent.value = navigator.userAgent
  screenResolution.value = `${screen.width}x${screen.height}`
  loadTime.value = getLoadTime()

  // 更新时间和窗口尺寸
  updateTime()
  updateWindowSize()
  updateMemoryInfo()

  // 设置定时器
  timeInterval = setInterval(() => {
    updateTime()
    updateMemoryInfo()
  }, 1000)

  // 监听窗口大小变化
  window.addEventListener('resize', updateWindowSize)
})

onUnmounted(() => {
  if (timeInterval) {
    clearInterval(timeInterval)
  }
  window.removeEventListener('resize', updateWindowSize)
})
</script>

<style scoped>
.environment-page {
  color: #fff;
}

.debug-section {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #333;
}

.debug-section:last-child {
  margin-bottom: 0;
  border-bottom: none;
}

.debug-section h4 {
  margin: 0 0 8px 0;
  color: #4caf50;
  font-size: 11px;
  font-weight: bold;
}

.info-item {
  display: flex;
  margin-bottom: 4px;
  align-items: flex-start;
}

.label {
  min-width: 70px;
  color: #999;
  font-weight: bold;
}

.value {
  flex: 1;
  color: #fff;
  word-break: break-word;
  font-size: 10px;
}
</style>
