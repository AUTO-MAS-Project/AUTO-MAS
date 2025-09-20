<template>
  <div
    v-if="isDev"
    class="debug-panel"
    :class="{ collapsed: isCollapsed, dragging: isDragging }"
    :style="{ left: `${panelPosition.x}px`, top: `${panelPosition.y}px` }"
  >
    <div class="debug-header">
      <span class="debug-title drag-handle" @mousedown="handleDragStart">
        调试面板 <span v-if="isDragging" class="drag-indicator">📌</span>
      </span>
      <button class="toggle-btn" @click="toggleCollapse" @mousedown.stop>
        {{ isCollapsed ? '展开' : '收起' }}
      </button>
    </div>

    <div v-if="!isCollapsed" class="debug-content" @mousedown.stop>
      <!-- 路由信息 -->
      <div class="debug-section">
        <h4>🛣️ 当前路由信息</h4>
        <div class="info-item">
          <span class="label">路径:</span>
          <span class="value">{{ currentRoute.path }}</span>
        </div>
        <div class="info-item">
          <span class="label">名称:</span>
          <span class="value">{{ currentRoute.name || '未命名' }}</span>
        </div>
        <div class="info-item">
          <span class="label">标题:</span>
          <span class="value">{{ currentRoute.meta?.title || '无标题' }}</span>
        </div>
        <div v-if="Object.keys(currentRoute.params).length > 0" class="info-item">
          <span class="label">参数:</span>
          <pre class="value">{{ JSON.stringify(currentRoute.params, null, 2) }}</pre>
        </div>
        <div v-if="Object.keys(currentRoute.query).length > 0" class="info-item">
          <span class="label">查询:</span>
          <pre class="value">{{ JSON.stringify(currentRoute.query, null, 2) }}</pre>
        </div>
      </div>

      <!-- 路由历史 -->
      <div class="debug-section">
        <h4>📚 路由历史 (最近10条)</h4>
        <div class="route-history">
          <div
            v-for="(route, index) in routeHistory"
            :key="index"
            class="history-item"
            :class="{ current: index === 0 }"
          >
            <span class="time">{{ route.time }}</span>
            <span class="path">{{ route.path }}</span>
            <span class="name">{{ route.name }}</span>
          </div>
        </div>
      </div>

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
      </div>

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
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, version, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

interface RouteHistoryItem {
  path: string
  name: string | null | undefined
  time: string
}

const route = useRoute()
const router = useRouter()

// 开发环境检测
const isDev = ref(process.env.NODE_ENV === 'development' || import.meta.env?.DEV === true)

// 面板状态
const isCollapsed = ref(false)
const isDragging = ref(false)

// 面板位置
const panelPosition = ref({
  x: window.innerWidth - 360, // 默认右侧位置
  y: 80, // 默认顶部位置
})

// 拖拽相关状态
const dragState = ref({
  startX: 0,
  startY: 0,
  startPanelX: 0,
  startPanelY: 0,
})

// 当前路由信息
const currentRoute = computed(() => ({
  path: route.path,
  name: route.name,
  params: route.params,
  query: route.query,
  meta: route.meta,
}))

// 路由历史记录
const routeHistory = ref<RouteHistoryItem[]>([])

// Vue版本
const vueVersion = ref(version)

// 当前时间
const currentTime = ref('')

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

// 更新时间
const updateTime = () => {
  currentTime.value = new Date().toLocaleString()
}

// 添加路由记录
const addRouteHistory = (newRoute: typeof route) => {
  const historyItem: RouteHistoryItem = {
    path: newRoute.path,
    name: typeof newRoute.name === 'string' ? newRoute.name : String(newRoute.name || ''),
    time: new Date().toLocaleTimeString(),
  }

  routeHistory.value.unshift(historyItem)
  // 只保留最近10条记录
  if (routeHistory.value.length > 10) {
    routeHistory.value = routeHistory.value.slice(0, 10)
  }
}

// 拖拽开始
const handleDragStart = (e: MouseEvent) => {
  isDragging.value = true
  dragState.value = {
    startX: e.clientX,
    startY: e.clientY,
    startPanelX: panelPosition.value.x,
    startPanelY: panelPosition.value.y,
  }

  document.addEventListener('mousemove', handleDragMove)
  document.addEventListener('mouseup', handleDragEnd)

  // 防止文本选择
  e.preventDefault()
}

// 拖拽移动
const handleDragMove = (e: MouseEvent) => {
  if (!isDragging.value) return

  const deltaX = e.clientX - dragState.value.startX
  const deltaY = e.clientY - dragState.value.startY

  let newX = dragState.value.startPanelX + deltaX
  let newY = dragState.value.startPanelY + deltaY

  // 边界检测，确保面板不会超出屏幕
  const panelWidth = isCollapsed.value ? 120 : 350
  const panelHeight = 400 // 预估高度

  newX = Math.max(0, Math.min(window.innerWidth - panelWidth, newX))
  newY = Math.max(0, Math.min(window.innerHeight - panelHeight, newY))

  panelPosition.value.x = newX
  panelPosition.value.y = newY
}

// 拖拽结束
const handleDragEnd = () => {
  isDragging.value = false
  document.removeEventListener('mousemove', handleDragMove)
  document.removeEventListener('mouseup', handleDragEnd)
}

// 切换面板状态
const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

// 导航到指定路由
const navigateTo = (path: string) => {
  router.push(path)
}

// 定时器
let timeInterval: NodeJS.Timeout

// 监听路由变化
watch(
  route,
  newRoute => {
    addRouteHistory(newRoute)
  },
  { immediate: true }
)

onMounted(() => {
  updateTime()
  timeInterval = setInterval(updateTime, 1000)

  // 添加键盘快捷键
  const handleKeyPress = (e: KeyboardEvent) => {
    // Ctrl + Shift + D 切换调试面板
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
      e.preventDefault()
      toggleCollapse()
    }
  }

  document.addEventListener('keydown', handleKeyPress)

  // 窗口大小改变时重新调整位置
  const handleResize = () => {
    const panelWidth = isCollapsed.value ? 120 : 350
    const panelHeight = 400

    panelPosition.value.x = Math.max(
      0,
      Math.min(window.innerWidth - panelWidth, panelPosition.value.x)
    )
    panelPosition.value.y = Math.max(
      0,
      Math.min(window.innerHeight - panelHeight, panelPosition.value.y)
    )
  }

  window.addEventListener('resize', handleResize)

  // 清理函数
  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeyPress)
    window.removeEventListener('resize', handleResize)
    document.removeEventListener('mousemove', handleDragMove)
    document.removeEventListener('mouseup', handleDragEnd)
  })
})

onUnmounted(() => {
  if (timeInterval) {
    clearInterval(timeInterval)
  }
})
</script>

<style scoped>
.debug-panel {
  position: fixed;
  top: 80px;
  right: 10px;
  width: 350px;
  background: rgba(0, 0, 0, 0.9);
  border: 1px solid #333;
  border-radius: 8px;
  color: #fff;
  font-size: 12px;
  z-index: 9999;
  backdrop-filter: blur(10px);
  transition: all 0.3s ease;
}

.debug-panel.collapsed {
  width: 120px;
}

.debug-panel.dragging {
  cursor: grabbing;
  transition: none; /* 拖动时禁用过渡效果 */
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  transform: scale(1.02);
}

.debug-header {
  padding: 8px 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px 8px 0 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  user-select: none;
}

.drag-handle {
  font-weight: bold;
  cursor: grab;
  flex: 1;
  padding: 4px 0;
}

.drag-handle:active {
  cursor: grabbing;
}

.toggle-btn {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 4px;
  color: #fff;
  padding: 4px 8px;
  font-size: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toggle-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  border-color: rgba(255, 255, 255, 0.5);
}

.debug-content {
  padding: 12px;
  max-height: 60vh;
  overflow-y: auto;
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
  min-width: 50px;
  color: #999;
  font-weight: bold;
}

.value {
  flex: 1;
  color: #fff;
  word-break: break-word;
}

.value pre {
  margin: 0;
  font-size: 10px;
  background: rgba(255, 255, 255, 0.1);
  padding: 4px;
  border-radius: 4px;
  white-space: pre-wrap;
}

.route-history {
  max-height: 120px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 10px;
}

.history-item.current {
  background: rgba(76, 175, 80, 0.2);
  border-radius: 4px;
  padding: 4px;
}

.history-item .time {
  color: #999;
  min-width: 60px;
}

.history-item .path {
  color: #2196f3;
  flex: 1;
}

.history-item .name {
  color: #4caf50;
  min-width: 60px;
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

.drag-indicator {
  animation: bounce 0.5s infinite alternate;
}

@keyframes bounce {
  0% {
    transform: translateY(0);
  }
  100% {
    transform: translateY(-2px);
  }
}

/* 滚动条样式 */
.debug-content::-webkit-scrollbar,
.route-history::-webkit-scrollbar {
  width: 4px;
}

.debug-content::-webkit-scrollbar-track,
.route-history::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
}

.debug-content::-webkit-scrollbar-thumb,
.route-history::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
}
</style>
