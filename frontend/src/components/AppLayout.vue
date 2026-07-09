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

    <a-layout-sider
      :width="SIDER_WIDTH"
      :theme="isDark ? 'dark' : 'light'"
      class="app-sider"
      :style="{
        background: 'var(--app-layout-sider-bg, var(--ant-color-bg-elevated))',
        borderRight: '1px solid var(--ant-color-border)',
      }"
    >
      <div class="sider-content">
        <a-menu
          v-model:selected-keys="selectedKeys"
          mode="inline"
          :theme="isDark ? 'dark' : 'light'"
          :items="declaredMainMenuItems"
          @click="onMenuClick"
        />
        <!-- 测试路由分隔区域 -->
        <a-menu
          v-if="isDevelopment"
          v-model:selected-keys="selectedKeys"
          mode="inline"
          :theme="isDark ? 'dark' : 'light'"
          class="dev-menu"
          :items="declaredDevMenuItems"
          @click="onMenuClick"
        />
        <a-menu
          v-model:selected-keys="selectedKeys"
          mode="inline"
          :theme="isDark ? 'dark' : 'light'"
          class="bottom-menu"
          :items="declaredBottomMenuItems"
          @click="onMenuClick"
        />
      </div>
    </a-layout-sider>

    <a-layout class="app-main-layout">
      <a-layout-content class="content-area">
        <router-view v-slot="{ Component, route: viewRoute }">
          <keep-alive :include="['Scheduler']">
            <component :is="Component" :key="viewRoute.path" />
          </keep-alive>
        </router-view>
        <transition name="hmr-fade">
          <div v-if="hmrOverlayVisible" class="hmr-soft-overlay" aria-live="polite">
            <div class="hmr-soft-panel">
              <LoadingOutlined class="hmr-soft-spinner" />
              <span>{{ hmrOverlayText }}</span>
            </div>
          </div>
        </transition>
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
  LoadingOutlined,
  RocketOutlined,
  SettingOutlined,
  ToolOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'
import { computed, h, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme.ts'
import { useRouteLock } from '../composables/useRouteLock.ts'
import { useAppBackground } from '../composables/useAppBackground.ts'
import { useWebSocket, type WebSocketBaseMessage } from '../composables/useWebSocket.ts'
import { OpenAPI } from '../api'
import {
  FALLBACK_PAGE_DECLARATIONS,
  normalizePageDeclarations,
  sortPageDeclarations,
  syncDeclaredPageRoutes,
  type PageDeclaration,
} from '../router/pageDeclarations.ts'
import type { MenuProps } from 'ant-design-vue'

const SIDER_WIDTH = 160

const router = useRouter()
const route = useRoute()
const { isDark } = useTheme()
const { isRouteLocked, triggerBlockCallback } = useRouteLock()
const {
  enabled: backgroundEnabled,
  cssVars: backgroundCssVars,
  loadBackground,
} = useAppBackground()
const { subscribe, unsubscribe } = useWebSocket()

let backgroundSubscriptionId = ''
let hmrOverlayTimer: ReturnType<typeof window.setTimeout> | undefined
let backgroundServiceSignature = ''
let hasBackgroundServiceSnapshot = false
const HMR_SOFT_RELOAD_FLAG = 'auto-mas-hmr-soft-reload'
const BACKGROUND_SERVICE_NAME = 'frontend_background'
const hmrOverlayVisible = ref(false)
const declaredPages = ref<PageDeclaration[]>(FALLBACK_PAGE_DECLARATIONS)
const hmrOverlayText = ref('正在重载插件界面')

onMounted(() => {
  void loadBackground()
  if (window.sessionStorage.getItem(HMR_SOFT_RELOAD_FLAG) === '1') {
    window.sessionStorage.removeItem(HMR_SOFT_RELOAD_FLAG)
    showHmrOverlay('插件界面已刷新', 800)
  }
  backgroundSubscriptionId = subscribe({ id: 'PluginSystem' }, handlePluginSystemMessage)
  syncDeclaredPageRoutes(router, declaredPages.value)
  void fetchInitialPluginSnapshot()
})

onUnmounted(() => {
  if (backgroundSubscriptionId) {
    unsubscribe(backgroundSubscriptionId)
    backgroundSubscriptionId = ''
  }
  if (hmrOverlayTimer !== undefined) {
    window.clearTimeout(hmrOverlayTimer)
    hmrOverlayTimer = undefined
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

interface PluginSystemSnapshotMessage {
  code?: number
  status?: string
  message?: string
  kind?: string
  pages?: PageDeclaration[]
  instances?: Array<{
    id?: string
    plugin?: string
    enabled?: boolean
    config?: Record<string, unknown>
  }>
  plugin_services?: Record<string, { provides?: string[] }>
}

const applyPageDeclarations = (rawPages: unknown) => {
  const pages = normalizePageDeclarations(rawPages)
  declaredPages.value = sortPageDeclarations(pages)
  syncDeclaredPageRoutes(router, declaredPages.value)
}

const toBackendUrl = (path: string) => {
  const base = (OpenAPI.BASE || 'http://localhost:36163').replace(/\/+$/, '')
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

const fetchInitialPluginSnapshot = async () => {
  try {
    const response = await fetch(toBackendUrl('/api/plugins/get'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    })
    const payload = (await response.json()) as PluginSystemSnapshotMessage
    if (!response.ok || (payload.code !== undefined && payload.code !== 200)) {
      throw new Error(payload.message || `HTTP ${response.status}`)
    }
    if (Array.isArray(payload.pages)) {
      applyPageDeclarations(payload.pages)
      refreshBackgroundFromSnapshotIfNeeded(payload)
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    console.warn(`加载插件页面声明失败，等待实时更新: ${message}`)
  }
}

const getBackgroundProviderPlugins = (payload: PluginSystemSnapshotMessage) => {
  const services = payload.plugin_services || {}
  return new Set(
    Object.entries(services)
      .filter(
        ([, service]) =>
          Array.isArray(service?.provides) && service.provides.includes(BACKGROUND_SERVICE_NAME)
      )
      .map(([plugin]) => plugin)
  )
}

const buildBackgroundServiceSignature = (payload: PluginSystemSnapshotMessage) => {
  const providers = getBackgroundProviderPlugins(payload)
  if (providers.size === 0) {
    return ''
  }

  const instances = Array.isArray(payload.instances) ? payload.instances : []
  return JSON.stringify(
    instances
      .filter(instance => instance.plugin && providers.has(instance.plugin))
      .map(instance => ({
        id: instance.id || '',
        plugin: instance.plugin || '',
        enabled: Boolean(instance.enabled),
        config: instance.config || {},
      }))
      .sort((a, b) => a.id.localeCompare(b.id))
  )
}

const refreshBackgroundFromSnapshotIfNeeded = (payload: PluginSystemSnapshotMessage) => {
  const nextSignature = buildBackgroundServiceSignature(payload)
  if (!hasBackgroundServiceSnapshot) {
    hasBackgroundServiceSnapshot = true
    backgroundServiceSignature = nextSignature
    return
  }

  if (nextSignature === backgroundServiceSignature) {
    return
  }

  backgroundServiceSignature = nextSignature
  void loadBackground()
}

const showHmrOverlay = (text: string, autoHideMs?: number) => {
  hmrOverlayText.value = text
  hmrOverlayVisible.value = true
  if (hmrOverlayTimer !== undefined) {
    window.clearTimeout(hmrOverlayTimer)
    hmrOverlayTimer = undefined
  }
  if (autoHideMs !== undefined) {
    hmrOverlayTimer = window.setTimeout(() => {
      hmrOverlayVisible.value = false
      hmrOverlayTimer = undefined
    }, autoHideMs)
  }
}

const hideHmrOverlaySoon = () => {
  showHmrOverlay('插件界面已更新', 650)
}

const refreshPluginFrontend = () => {
  if (!isDevelopment.value) {
    return
  }
  const hot = (import.meta as any).hot
  showHmrOverlay('正在刷新插件前端')
  window.sessionStorage.setItem(HMR_SOFT_RELOAD_FLAG, '1')
  window.setTimeout(() => {
    if (hot?.invalidate) {
      hot.invalidate()
      window.setTimeout(() => {
        window.location.reload()
      }, 1200)
      return
    }
    window.location.reload()
  }, 80)
}

const handlePluginSystemMessage = (message: WebSocketBaseMessage) => {
  const payload = message.data as PluginSystemSnapshotMessage | PluginSystemHmrMessage | undefined
  if (!payload || typeof payload !== 'object') {
    return
  }

  if (Array.isArray((payload as PluginSystemSnapshotMessage).pages)) {
    const snapshotPayload = payload as PluginSystemSnapshotMessage
    applyPageDeclarations(snapshotPayload.pages)
    refreshBackgroundFromSnapshotIfNeeded(snapshotPayload)
  }

  if (payload.kind !== 'hmr') {
    return
  }

  const hmrPayload = payload as PluginSystemHmrMessage
  if (hmrPayload.status === 'running') {
    showHmrOverlay('正在重载插件界面')
  } else if (hmrPayload.status === 'success' || hmrPayload.status === 'error') {
    hideHmrOverlaySoon()
  }
  if (hmrPayload.status === 'success' && hmrPayload.action === 'frontend_refresh') {
    refreshPluginFrontend()
  }
}

const pageIconMap: Record<string, any> = {
  home: HomeOutlined,
  script: FileTextOutlined,
  plan: CalendarOutlined,
  emulator: DatabaseOutlined,
  plugin: ApiOutlined,
  market: AppstoreOutlined,
  queue: UnorderedListOutlined,
  game: RocketOutlined,
  scheduler: ControlOutlined,
  history: HistoryOutlined,
  tool: ToolOutlined,
  settings: SettingOutlined,
  dev: SettingOutlined,
  api: ApiOutlined,
  app: AppstoreOutlined,
}

const buildMenuItems = (section: string) =>
  declaredPages.value
    .filter(page => page.visible && page.section === section)
    .filter(page => !page.dev_only || isDevelopment.value)
    .map(page => ({
      key: page.path,
      label: page.menu_label,
      icon: icon(pageIconMap[page.icon] || AppstoreOutlined),
    }))

const declaredMainMenuItems = computed(() => buildMenuItems('main'))
const declaredDevMenuItems = computed(() => buildMenuItems('dev'))
const declaredBottomMenuItems = computed(() => buildMenuItems('bottom'))

const allItems = computed(() => [
  ...declaredMainMenuItems.value,
  ...(isDevelopment.value ? declaredDevMenuItems.value : []),
  ...declaredBottomMenuItems.value,
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
    var(--ant-color-bg-elevated) var(--app-background-elevated-opacity),
    transparent
  );
  --app-background-panel-bg: color-mix(
    in srgb,
    var(--ant-color-bg-container) var(--app-background-panel-opacity),
    transparent
  );
  --app-layout-sider-bg: color-mix(
    in srgb,
    var(--ant-color-bg-elevated) var(--app-background-sider-opacity),
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
.app-layout-shell.has-background :deep(.ant-tabs-content-holder),
.app-layout-shell.has-background :deep(.ant-alert),
.app-layout-shell.has-background :deep(.ant-descriptions-view),
.app-layout-shell.has-background :deep(.ant-descriptions-item-label),
.app-layout-shell.has-background :deep(.ant-descriptions-item-content),
.app-layout-shell.has-background :deep(.ant-form-item),
.app-layout-shell.has-background :deep(.schema-item) {
  background: var(--app-background-panel-bg) !important;
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
  position: relative;
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

.hmr-soft-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: color-mix(in srgb, var(--ant-color-bg-layout) 70%, transparent);
  backdrop-filter: blur(4px);
  pointer-events: none;
}

.hmr-soft-panel {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 10px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-elevated);
  box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
  font-size: 14px;
  line-height: 1.4;
}

.hmr-soft-spinner {
  color: var(--ant-color-primary);
  font-size: 18px;
}

.hmr-fade-enter-active,
.hmr-fade-leave-active {
  transition:
    opacity 0.18s ease,
    backdrop-filter 0.18s ease;
}

.hmr-fade-enter-from,
.hmr-fade-leave-to {
  opacity: 0;
  backdrop-filter: blur(0);
}
</style>

<!-- 使用标准 Sider 布局，去除 fixed 与 marginLeft，保持菜单样式与滚动行为 -->
