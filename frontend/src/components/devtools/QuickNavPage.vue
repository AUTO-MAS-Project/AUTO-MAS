<template>
  <div class="quick-nav-page">
    <!-- 手动导航 -->
    <div class="debug-section">
      <h4>🎯 手动导航</h4>
      <div class="manual-nav">
        <input
          v-model="manualPath"
          placeholder="输入路径 (例: /home, /scripts)"
          class="path-input"
          @keyup.enter="navigateToManualPath"
        />
        <button class="nav-go-btn" @click="navigateToManualPath">跳转</button>
      </div>
    </div>

    <!-- 快捷导航 -->
    <div class="debug-section">
      <h4>🚀 快捷导航</h4>
      <div class="quick-nav">
        <button
          v-for="route in commonRoutes"
          :key="route.path"
          class="nav-btn"
          :class="{ active: currentRoute.path === route.path }"
          @click="navigateTo(route.path)"
        >
          {{ route.title }}
        </button>
      </div>
    </div>

    <!-- 开发工具 -->
    <div class="debug-section">
      <h4>🛠️ 开发工具</h4>
      <div class="tool-actions">
        <button class="action-btn" @click="clearStorage">清除存储</button>
        <button class="action-btn" @click="reloadPage">重新加载</button>
        <button class="action-btn" @click="toggleConsole">切换控制台</button>
        <button class="action-btn" @click="openDevtool">打开开发者工具</button>
        <!-- 新增：3s 后触发 Popup 弹窗 -->
        <button class="action-btn" :disabled="isPopupScheduled" @click="schedulePopup">
          {{ isPopupScheduled ? '已计划：3s 后弹窗...' : '3s 后触发 Popup' }}
        </button>
      </div>
    </div>

    <!-- 快捷键说明 -->
    <div class="debug-section">
      <h4>⌨️ 快捷键</h4>
      <div class="shortcut-list">
        <div class="shortcut-item">
          <span class="keys">Ctrl + Shift + D</span>
          <span class="desc">切换调试面板</span>
        </div>
        <div class="shortcut-item">
          <span class="keys">F12</span>
          <span class="desc">开发者工具</span>
        </div>
        <div class="shortcut-item">
          <span class="keys">Ctrl + R</span>
          <span class="desc">刷新页面</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, getCurrentInstance, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { logger } from '@/utils/logger'
import { getLogger } from '@/utils/logger'

const quickNavLogger = getLogger('快速导航页面')

const route = useRoute()
const router = useRouter()

// 当前路由信息
const currentRoute = computed(() => ({
  path: route.path,
  name: route.name,
  params: route.params,
  query: route.query,
  meta: route.meta,
}))

// 常用路由
const commonRoutes = [
  { path: '/initialization', title: '初始化' },
  { path: '/home', title: '主页' },
  { path: '/scripts', title: '脚本管理' },
  { path: '/plans', title: '计划管理' },
  { path: '/queue', title: '调度队列' },
  { path: '/settings', title: '设置' },
  { path: '/logs', title: '日志' },
]

// 导航到指定路由
const navigateTo = (path: string) => {
  router.push(path)
}

// 手动导航路径
const manualPath = ref('')

// 手动导航
const navigateToManualPath = () => {
  if (manualPath.value.trim()) {
    let path = manualPath.value.trim()
    // 确保路径以 / 开头
    if (!path.startsWith('/')) {
      path = '/' + path
    }
    router.push(path)
    manualPath.value = '' // 清空输入框
  }
}

const openDevtool = () => {
  try {
    if ((window as any).electronAPI?.openDevTools) {
      ;(window as any).electronAPI.openDevTools()
      quickNavLogger.info('✅ 开发者工具已打开')
    } else {
      quickNavLogger.warn('⚠️ 开发者工具API不可用')
    }
  } catch (error) {
    quickNavLogger.error('❌ 打开开发者工具失败:', error)
  }
}

// 清除本地存储
const clearStorage = () => {
  try {
    const confirmed = confirm('确定要清除所有本地存储数据吗？这将清除应用的所有缓存数据。')
    if (confirmed) {
      localStorage.clear()
      sessionStorage.clear()
      // 清除IndexedDB（如果有）
      if (window.indexedDB) {
        // 这里可以添加更复杂的IndexedDB清理逻辑
      }
      quickNavLogger.info('✅ 本地存储已清除')
      alert('本地存储已清除，建议刷新页面')
    }
  } catch (error) {
    quickNavLogger.error('❌ 清除存储失败:', error)
  }
}

// 重新加载页面
const reloadPage = () => {
  try {
    quickNavLogger.info('🔄 页面重新加载中...')
    window.location.reload()
  } catch (error) {
    quickNavLogger.error('❌ 页面重载失败:', error)
  }
}

// 切换控制台（显示有用的调试信息）
const toggleConsole = () => {
  try {
    quickNavLogger.info('当前URL:', window.location.href)
    quickNavLogger.info('用户代理:', navigator.userAgent)
    quickNavLogger.info('开发模式:', process.env.NODE_ENV === 'development')
    quickNavLogger.info('Vue版本:', getCurrentInstance()?.appContext.app.version || 'Unknown')
    quickNavLogger.info('localStorage项目数:', Object.keys(localStorage).length)
    quickNavLogger.info('sessionStorage项目数:', Object.keys(sessionStorage).length)
    if ((window as any).wsDebug) {
      quickNavLogger.info('WebSocket调试:', (window as any).wsDebug)
    }
  } catch (error) {
    quickNavLogger.error('❌ 获取调试信息失败:', error)
  }
}

// 新增：3s 后触发 Popup 弹窗
const isPopupScheduled = ref(false)
const schedulePopup = () => {
  if (isPopupScheduled.value) return
  isPopupScheduled.value = true

  setTimeout(() => {
    const data = {
      title: '调试弹窗',
      message: '这是在 3 秒后自动触发的 Popup 测试弹窗。',
      options: ['确定', '取消'],
      messageId: '',
    }

    router.push({
      path: '/popup',
      query: { data: encodeURIComponent(JSON.stringify(data)) },
    })

    // 计划触发一次后即可再次使用
    isPopupScheduled.value = false
  }, 3000)
}
</script>

<style scoped>
.quick-nav-page {
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

.quick-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.nav-btn {
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 10px;
  transition: all 0.2s ease;
}

.nav-btn:hover {
  background: rgba(255, 255, 255, 0.2);
}

.nav-btn.active {
  background: #4caf50;
  border-color: #4caf50;
}

.tool-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.action-btn {
  padding: 4px 8px;
  background: rgba(255, 152, 0, 0.2);
  border: 1px solid rgba(255, 152, 0, 0.3);
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 10px;
  transition: all 0.2s ease;
}

.action-btn:hover {
  background: rgba(255, 152, 0, 0.3);
  border-color: rgba(255, 152, 0, 0.5);
}

.shortcut-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.shortcut-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 10px;
}

.keys {
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 4px;
  border-radius: 2px;
  font-family: monospace;
  color: #ffd700;
}

.desc {
  color: #999;
}

.manual-nav {
  display: flex;
  gap: 8px;
  align-items: center;
}

.path-input {
  flex: 1;
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  color: #fff;
  font-size: 10px;
  outline: none;
  transition: all 0.2s ease;
}

.path-input:focus {
  background: rgba(255, 255, 255, 0.15);
  border-color: #4caf50;
}

.path-input::placeholder {
  color: rgba(255, 255, 255, 0.5);
}

.nav-go-btn {
  padding: 4px 12px;
  background: #2196f3;
  border: 1px solid #1976d2;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  font-size: 10px;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.nav-go-btn:hover {
  background: #1976d2;
  border-color: #1565c0;
}
</style>
