<template>
  <div class="quick-nav-page">
    <!-- 快捷导航 -->
    <div class="debug-section">
      <h4>🚀 快捷导航</h4>
      <div class="quick-nav">
        <button
          v-for="route in commonRoutes"
          :key="route.path"
          @click="navigateTo(route.path)"
          class="nav-btn"
          :class="{ active: currentRoute.path === route.path }"
        >
          {{ route.title }}
        </button>
      </div>
    </div>

    <!-- 开发工具 -->
    <div class="debug-section">
      <h4>🛠️ 开发工具</h4>
      <div class="tool-actions">
        <button @click="clearStorage" class="action-btn">清除存储</button>
        <button @click="reloadPage" class="action-btn">重新加载</button>
        <button @click="toggleConsole" class="action-btn">切换控制台</button>
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
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

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

// 清除本地存储
const clearStorage = () => {
  if (confirm('确定要清除所有本地存储数据吗？')) {
    localStorage.clear()
    sessionStorage.clear()
    console.log('本地存储已清除')
  }
}

// 重新加载页面
const reloadPage = () => {
  window.location.reload()
}

// 切换控制台（仅在开发环境有效）
const toggleConsole = () => {
  if (process.env.NODE_ENV === 'development') {
    console.log('控制台切换功能仅在开发环境可用')
  }
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
</style>
