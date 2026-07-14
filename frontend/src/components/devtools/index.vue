<template>
  <div
    v-if="isDev"
    class="debug-panel"
    :class="{ collapsed: isCollapsed, dragging: isDragging }"
    :style="{ left: `${panelPosition.x}px`, top: `${panelPosition.y}px` }"
  >
    <div class="debug-header">
      <span class="debug-title drag-handle" @mousedown="startDrag">
        调试面板 <span v-if="isDragging" class="drag-indicator">📌</span>
      </span>
      <div class="header-actions">
        <button class="toggle-btn" @click="toggleCollapse" @mousedown.stop>
          {{ isCollapsed ? '展开' : '收起' }}
        </button>
      </div>
    </div>

    <div v-if="!isCollapsed" class="debug-content" @mousedown.stop>
      <!-- 页面切换选项卡 -->
      <div class="debug-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-btn"
          :class="{ active: activeTab === tab.key }"
          @click="setActiveTab(tab.key)"
        >
          {{ tab.icon }} {{ tab.title }}
        </button>
      </div>

      <!-- 页面内容 -->
      <div class="debug-pages">
        <component :is="currentComponent" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useEventListener, useWindowSize } from '@vueuse/core'
import RouteInfoPage from './RouteInfoPage.vue'
import EnvironmentPage from './EnvironmentPage.vue'
import QuickNavPage from './QuickNavPage.vue'
import MessageTestPage from './MessageTestPage.vue'
import BackendLaunchPage from './BackendLaunchPage.vue'

// 调试页面配置
const tabs = [
  { key: 'route', title: '路由', icon: '🛣️', component: RouteInfoPage },
  { key: 'env', title: '环境', icon: '⚙️', component: EnvironmentPage },
  { key: 'backend', title: '后端', icon: '🚀', component: BackendLaunchPage },
  { key: 'nav', title: '导航', icon: '🧭', component: QuickNavPage },
  { key: 'message', title: '消息', icon: '💬', component: MessageTestPage },
]

// 开发环境检测
const isDev = ref(
  process.env.NODE_ENV === 'development' ||
    import.meta.env.DEV === true ||
    window.location.hostname === 'localhost'
)

// 面板状态
const isCollapsed = ref(false)
const isDragging = ref(false)
const activeTab = ref('backend') // 默认显示后端页面

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

// 当前组件
const currentComponent = computed(() => {
  const tab = tabs.find(t => t.key === activeTab.value)
  return tab?.component || RouteInfoPage
})

// 设置活动选项卡
const setActiveTab = (tabKey: string) => {
  activeTab.value = tabKey
}

// 使用 VueUse 的 useWindowSize 监听窗口大小
const { width: windowWidth, height: windowHeight } = useWindowSize()

// 拖拽开始
const handleDragStart = (e: MouseEvent) => {
  isDragging.value = true
  dragState.value = {
    startX: e.clientX,
    startY: e.clientY,
    startPanelX: panelPosition.value.x,
    startPanelY: panelPosition.value.y,
  }

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

  newX = Math.max(0, Math.min(windowWidth.value - panelWidth, newX))
  newY = Math.max(0, Math.min(windowHeight.value - panelHeight, newY))

  panelPosition.value.x = newX
  panelPosition.value.y = newY
}

// 拖拽结束
const handleDragEnd = () => {
  isDragging.value = false
}

// 使用 VueUse 的 useEventListener 管理拖拽事件
let cleanupDrag: (() => void) | null = null

const startDrag = (e: MouseEvent) => {
  handleDragStart(e)

  const cleanupMove = useEventListener(document, 'mousemove', handleDragMove)
  const cleanupUp = useEventListener(document, 'mouseup', () => {
    handleDragEnd()
    if (cleanupDrag) {
      cleanupDrag()
      cleanupDrag = null
    }
  })

  cleanupDrag = () => {
    cleanupMove()
    cleanupUp()
  }
}

// 切换面板状态
const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value

  // 当折叠状态改变时，调整位置以适应新尺寸
  const panelWidth = isCollapsed.value ? 120 : 350
  const panelHeight = 400

  panelPosition.value.x = Math.max(
    0,
    Math.min(windowWidth.value - panelWidth, panelPosition.value.x)
  )
  panelPosition.value.y = Math.max(
    0,
    Math.min(windowHeight.value - panelHeight, panelPosition.value.y)
  )
}

// 使用 VueUse 的 useEventListener 监听键盘快捷键
useEventListener(document, 'keydown', (e: KeyboardEvent) => {
  // Ctrl + Shift + D 切换调试面板
  if (e.ctrlKey && e.shiftKey && e.key === 'D') {
    e.preventDefault()
    toggleCollapse()
  }
})

onMounted(() => {
  // 初始化时确保面板在可见区域
  const panelWidth = isCollapsed.value ? 120 : 350
  const panelHeight = 400

  panelPosition.value.x = Math.max(
    0,
    Math.min(windowWidth.value - panelWidth, panelPosition.value.x)
  )
  panelPosition.value.y = Math.max(
    0,
    Math.min(windowHeight.value - panelHeight, panelPosition.value.y)
  )
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
  transition: none;
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

.header-actions {
  display: flex;
  gap: 4px;
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
  padding: 0;
  max-height: 60vh;
  overflow: hidden;
}

.debug-tabs {
  display: flex;
  background: rgba(255, 255, 255, 0.05);
  border-bottom: 1px solid #333;
}

.tab-btn {
  flex: 1;
  padding: 8px 4px;
  background: transparent;
  border: none;
  color: #999;
  cursor: pointer;
  font-size: 10px;
  transition: all 0.2s ease;
  border-right: 1px solid rgba(255, 255, 255, 0.1);
}

.tab-btn:last-child {
  border-right: none;
}

.tab-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.tab-btn.active {
  background: #4caf50;
  color: #fff;
}

.debug-pages {
  padding: 12px;
  max-height: calc(60vh - 40px);
  overflow-y: auto;
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

.debug-pages::-webkit-scrollbar {
  width: 4px;
}

.debug-pages::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
}

.debug-pages::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
}
</style>
