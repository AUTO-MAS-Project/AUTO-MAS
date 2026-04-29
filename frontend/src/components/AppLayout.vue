<template>
  <a-layout
    class="app-layout-shell"
    :class="{ 'has-background': backgroundEnabled }"
    :style="backgroundCssVars"
  >
    <div v-if="backgroundEnabled" class="app-background-layer" aria-hidden="true">
      <div class="app-background-image" />
      <div class="app-background-overlay" />
    </div>

    <a-layout-sider :width="SIDER_WIDTH" :theme="isDark ? 'dark' : 'light'" class="app-sider" :style="{
      background: 'var(--app-layout-sider-bg, var(--ant-color-bg-elevated))',
      borderRight: '1px solid var(--ant-color-border)',
    }">
      <div class="sider-content">
        <a-menu v-model:selected-keys="selectedKeys" mode="inline" :theme="isDark ? 'dark' : 'light'"
          :items="mainMenuItems" @click="onMenuClick" />
        <!-- 测试路由分隔区域 -->
        <a-menu v-if="isDevelopment" v-model:selected-keys="selectedKeys" mode="inline"
          :theme="isDark ? 'dark' : 'light'" class="dev-menu" :items="devMenuItems" @click="onMenuClick" />
        <a-menu v-model:selected-keys="selectedKeys" mode="inline" :theme="isDark ? 'dark' : 'light'"
          class="bottom-menu" :items="bottomMenuItems" @click="onMenuClick" />
      </div>
    </a-layout-sider>

    <a-layout class="app-main-layout">
      <a-layout-content class="content-area">
        <router-view v-slot="{ Component, route }">
          <keep-alive :include="['Scheduler']">
            <component :is="Component" :key="route.path" />
          </keep-alive>
        </router-view>
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script lang="ts" setup>
import {
  ApiOutlined,
  AppstoreOutlined,
  CalendarOutlined,
  ControlOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  HistoryOutlined,
  HomeOutlined,
  SettingOutlined,
  ToolOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'
import { computed, h, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme.ts'
import { useRouteLock } from '../composables/useRouteLock.ts'
import { useAppBackground } from '../composables/useAppBackground.ts'
import { useWebSocket, type WebSocketBaseMessage } from '../composables/useWebSocket.ts'
import type { MenuProps } from 'ant-design-vue'

const SIDER_WIDTH = 160

const router = useRouter()
const route = useRoute()
const { isDark } = useTheme()
const { isRouteLocked, triggerBlockCallback } = useRouteLock()
const { enabled: backgroundEnabled, cssVars: backgroundCssVars, loadBackground } = useAppBackground()
const { subscribe, unsubscribe } = useWebSocket()

let backgroundSubscriptionId = ''
let backgroundRefreshTimer: ReturnType<typeof window.setTimeout> | undefined

onMounted(() => {
  void loadBackground()
  backgroundSubscriptionId = subscribe({ id: 'PluginSystem' }, handlePluginSystemMessage)
  backgroundRefreshTimer = window.setTimeout(() => {
    void loadBackground()
  }, 1500)
})

onUnmounted(() => {
  if (backgroundSubscriptionId) {
    unsubscribe(backgroundSubscriptionId)
    backgroundSubscriptionId = ''
  }
  if (backgroundRefreshTimer !== undefined) {
    window.clearTimeout(backgroundRefreshTimer)
    backgroundRefreshTimer = undefined
  }
})

// 工具：生成菜单项
const icon = (Comp: any) => () => h(Comp)

// 判断是否为开发环境
const isDevelopment = computed(() => {
  return (
    process.env.NODE_ENV === 'development' ||
    (import.meta as any).env?.DEV === true ||
    window.location.hostname === 'localhost'
  )
})

interface PluginSystemHmrMessage {
  kind: 'hmr'
  plugin?: string | null
  changed_files?: string[]
  action?: string
  status?: string
}

const isBackgroundHmr = (payload: PluginSystemHmrMessage) => {
  if (payload.plugin === 'background') {
    return true
  }
  return (payload.changed_files || []).some(file => {
    const normalized = file.replace(/\\/g, '/')
    return normalized.startsWith('plugins/background/') || normalized.includes('/assets/')
  })
}

const refreshPluginFrontend = () => {
  if (!isDevelopment.value) {
    return
  }
  const hot = (import.meta as any).hot
  if (hot?.invalidate) {
    hot.invalidate()
    return
  }
  window.location.reload()
}

const handlePluginSystemMessage = (message: WebSocketBaseMessage) => {
  const payload = message.data as { kind?: string } | PluginSystemHmrMessage | undefined
  if (!payload || typeof payload !== 'object') {
    return
  }

  if (payload.kind !== 'hmr') {
    void loadBackground()
    return
  }

  const hmrPayload = payload as PluginSystemHmrMessage
  if (isBackgroundHmr(hmrPayload)) {
    void loadBackground()
  }
  if (hmrPayload.status === 'success' && hmrPayload.action === 'frontend_refresh') {
    refreshPluginFrontend()
  }
}

const mainMenuItems = [
  { key: '/home', label: '主页', icon: icon(HomeOutlined) },
  { key: '/scripts', label: '脚本管理', icon: icon(FileTextOutlined) },
  { key: '/plans', label: '计划管理', icon: icon(CalendarOutlined) },
  { key: '/emulators', label: '模拟器管理', icon: icon(DatabaseOutlined) },
  { key: '/plugins', label: '插件管理', icon: icon(ApiOutlined) },
  { key: '/plugins-market', label: '插件市场', icon: icon(AppstoreOutlined) },
  { key: '/queue', label: '调度队列', icon: icon(UnorderedListOutlined) },
  { key: '/scheduler', label: '调度中心', icon: icon(ControlOutlined) },
]

// 开发环境专用菜单项
const devMenuItems = [
  { key: '/TestRouter', label: '测试路由', icon: icon(SettingOutlined) },
  { key: '/OCRdev', label: 'OCR测试', icon: icon(SettingOutlined) },
  { key: '/WSdev', label: 'WebSocket测试', icon: icon(ApiOutlined) },
  { key: '/OverlayMaskDev', label: '遮罩彩蛋测试', icon: icon(SettingOutlined) },
]

const bottomMenuItems = [
  { key: '/history', label: '历史记录', icon: icon(HistoryOutlined) },
  { key: '/tools', label: '工具', icon: icon(ToolOutlined) },
  { key: '/settings', label: '设置', icon: icon(SettingOutlined) },
]

const allItems = computed(() => [
  ...mainMenuItems,
  ...(isDevelopment.value ? devMenuItems : []),
  ...bottomMenuItems,
])

// 选中项：根据当前路径前缀匹配
const selectedKeys = computed(() => {
  const path = route.path
  const exactMatched = allItems.value.find(i => path === String(i.key))
  if (exactMatched) {
    return [exactMatched.key]
  }

  // 退化到前缀匹配时，优先选择“最长前缀”，避免 /plugins 命中 /plugins-market。
  const prefixMatched = allItems.value
    .filter(i => path.startsWith(String(i.key)))
    .sort((a, b) => String(b.key).length - String(a.key).length)[0]

  const matched = prefixMatched
  return [matched?.key || '/home']
})

const onMenuClick: MenuProps['onClick'] = info => {
  const target = String(info.key)

  // 检查路由是否被锁定
  if (isRouteLocked.value) {
    // 如果路由被锁定，触发回调而不进行路由跳转
    triggerBlockCallback(target)
    return
  }

  if (route.path !== target) router.push(target)
}
</script>

<style scoped>
.app-layout-shell {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
  background: var(--ant-color-bg-layout);
}

.app-layout-shell.has-background {
  background: transparent;
  --app-background-card-bg: color-mix(
    in srgb,
    var(--ant-color-bg-container) var(--app-background-card-opacity),
    transparent
  );
  --app-background-card-elevated-bg: color-mix(
    in srgb,
    var(--ant-color-bg-elevated) var(--app-background-card-opacity),
    transparent
  );
  --app-layout-sider-bg: color-mix(
    in srgb,
    var(--ant-color-bg-elevated) 88%,
    transparent
  );
}

.app-layout-shell.has-background :deep(.plugin-page) {
  background: transparent;
}

.app-layout-shell.has-background :deep(.ant-card),
.app-layout-shell.has-background :deep(.ant-card-head),
.app-layout-shell.has-background :deep(.ant-card-body),
.app-layout-shell.has-background :deep(.ant-list),
.app-layout-shell.has-background :deep(.ant-table),
.app-layout-shell.has-background :deep(.ant-table-container),
.app-layout-shell.has-background :deep(.ant-table-thead > tr > th),
.app-layout-shell.has-background :deep(.ant-table-tbody > tr > td),
.app-layout-shell.has-background :deep(.ant-collapse),
.app-layout-shell.has-background :deep(.ant-collapse-item),
.app-layout-shell.has-background :deep(.ant-collapse-content),
.app-layout-shell.has-background :deep(.ant-tabs-content-holder) {
  background: var(--app-background-card-bg) !important;
}

.app-layout-shell.has-background :deep(.ant-modal-content),
.app-layout-shell.has-background :deep(.ant-popover-inner),
.app-layout-shell.has-background :deep(.ant-drawer-content),
.app-layout-shell.has-background :deep(.ant-select-dropdown),
.app-layout-shell.has-background :deep(.ant-picker-dropdown .ant-picker-panel-container) {
  background: var(--app-background-card-elevated-bg) !important;
}

.app-background-layer {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
  background: var(--ant-color-bg-layout);
}

.app-background-image {
  position: absolute;
  inset: -48px;
  background-image: var(--app-background-image);
  background-size: var(--app-background-size);
  background-position: var(--app-background-position);
  background-repeat: no-repeat;
  opacity: var(--app-background-opacity);
  filter: blur(var(--app-background-blur)) brightness(var(--app-background-brightness));
  transform: scale(1.03);
}

.app-background-overlay {
  position: absolute;
  inset: 0;
  background: var(--ant-color-bg-layout);
  opacity: var(--app-background-overlay-opacity);
}

.app-sider,
.app-main-layout {
  position: relative;
  z-index: 1;
}

.app-main-layout {
  flex: 1;
  min-width: 0;
  background: transparent;
}

.sider-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 10px 3px;
}

.sider-content :deep(.ant-menu) {
  border-inline-end: none !important;
  background: transparent !important;
}

/* 菜单项外框居中（左右留空），内容左对齐 */
.sider-content :deep(.ant-menu .ant-menu-item) {
  color: var(--ant-color-text);
  margin: 2px auto;
  /* 水平居中 */
  width: calc(100% - 16px);
  /* 两侧各留 8px 空隙 */
  border-radius: 6px;
  padding: 5px 16px !important;
  /* 左右内边距 */
  line-height: 36px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  /* 左对齐图标与文字 */
  gap: 6px;
  transition:
    background 0.16s ease,
    color 0.16s ease;
  text-align: left;
}

.sider-content :deep(.ant-menu .ant-menu-item .anticon) {
  color: var(--ant-color-text-secondary);
  font-size: 18px;
  line-height: 1;
  transition: color 0.16s ease;
  margin-right: 0;
}

/* Hover */
.sider-content :deep(.ant-menu .ant-menu-item:hover) {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-text);
}

.sider-content :deep(.ant-menu .ant-menu-item:hover .anticon) {
  color: var(--ant-color-text);
}

/* Selected */
.sider-content :deep(.ant-menu .ant-menu-item-selected) {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-text) !important;
  font-weight: 500;
}

.sider-content :deep(.ant-menu .ant-menu-item-selected .anticon) {
  color: var(--ant-color-text-secondary);
}

.sider-content :deep(.ant-menu-light .ant-menu-item::after),
.sider-content :deep(.ant-menu-dark .ant-menu-item::after) {
  display: none;
}

/* 开发菜单区域 - 添加上边距以创建视觉分隔 */
.dev-menu {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border);
}

.bottom-menu {
  margin-top: auto;
}

.content-area {
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  overflow: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
  padding: 32px 32px 48px;
  background: transparent;
}

.content-area::-webkit-scrollbar {
  display: none;
}

</style>

<!-- 使用标准 Sider 布局，去除 fixed 与 marginLeft，保持菜单样式与滚动行为 -->
