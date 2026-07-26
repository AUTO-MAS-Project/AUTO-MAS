<template>
  <a-layout
    class="app-layout-shell"
    :class="{ 'has-background': backgroundEnabled }"
    :style="backgroundCssVars"
    :data-background-source="backgroundSource"
  >
    <a href="#app-main-content" class="skip-to-content" @click.prevent="focusMainContent">
      跳转到主内容
    </a>
    <AppBackgroundLayer />

    <a-layout class="app-window-body">
      <AppSider
        :main-items="mainItems"
        :bottom-items="bottomItems"
        :dev-items="devItems"
        :selected-keys="selectedKeys"
        :collapsed="collapsed"
        :is-development="isDevelopment"
        @menu-click="onMenuClick"
        @search="handleGlobalSearch"
        @toggle-collapse="toggleCollapse"
      />

      <AppContentArea :hmr-overlay-visible="hmrOverlayVisible" :hmr-overlay-text="hmrOverlayText" />
    </a-layout>
  </a-layout>
</template>

<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref, watch, type WatchStopHandle } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRouteLock } from '../composables/useRouteLock.ts'
import { useAppBackground } from '../composables/useAppBackground.ts'
import { useWebSocket, type WebSocketBaseMessage } from '../composables/useWebSocket.ts'
import { useAppInitialization } from '../composables/useAppInitialization.ts'
import { OpenAPI } from '@/api'
import { authenticatedApiFetch } from '@/utils/httpSecurity'
import {
  dedupePageDeclarations,
  FALLBACK_PAGE_DECLARATIONS,
  normalizePageDeclarations,
  sortPageDeclarations,
  syncDeclaredPageRoutes,
  type PageDeclaration,
} from '../router/pageDeclarations.ts'
import AppBackgroundLayer from './app-shell/AppBackgroundLayer.vue'
import AppSider from './app-shell/AppSider.vue'
import AppContentArea from './app-shell/AppContentArea.vue'

const SIDER_COLLAPSED_KEY = 'app-sider-collapsed'
const HMR_SOFT_RELOAD_FLAG = 'auto-mas-hmr-soft-reload'
const BACKGROUND_SERVICE_NAME = 'frontend_background'
const logger = window.electronAPI.getLogger('应用布局')

const router = useRouter()
const route = useRoute()
const { isRouteLocked, triggerBlockCallback } = useRouteLock()
const {
  enabled: backgroundEnabled,
  source: backgroundSource,
  cssVars: backgroundCssVars,
  loadBackground,
} = useAppBackground()
const { subscribe, unsubscribe } = useWebSocket()
const { isBootstrapping } = useAppInitialization()

let backgroundSubscriptionId = ''
let stopBootstrapWatch: WatchStopHandle | undefined
let hmrOverlayTimer: number | undefined
let backgroundServiceSignature = ''
let hasBackgroundServiceSnapshot = false

const hmrOverlayVisible = ref(false)
const declaredPages = ref<PageDeclaration[]>(FALLBACK_PAGE_DECLARATIONS)
const collapsed = ref(false)
const hmrOverlayText = ref('正在重载插件界面')

onMounted(() => {
  collapsed.value = localStorage.getItem(SIDER_COLLAPSED_KEY) === 'true'

  if (window.sessionStorage.getItem(HMR_SOFT_RELOAD_FLAG) === '1') {
    window.sessionStorage.removeItem(HMR_SOFT_RELOAD_FLAG)
    showHmrOverlay('插件界面已刷新', 800)
  }
  backgroundSubscriptionId = subscribe({ id: 'PluginSystem' }, handlePluginSystemMessage)
  syncDeclaredPageRoutes(router, declaredPages.value)

  const loadBackendState = () => {
    void loadBackground()
    void fetchInitialPluginSnapshot()
  }

  if (isBootstrapping.value) {
    stopBootstrapWatch = watch(isBootstrapping, bootstrapping => {
      if (bootstrapping) return
      stopBootstrapWatch?.()
      stopBootstrapWatch = undefined
      loadBackendState()
    })
  } else {
    loadBackendState()
  }
})

onUnmounted(() => {
  stopBootstrapWatch?.()
  stopBootstrapWatch = undefined
  if (backgroundSubscriptionId) {
    unsubscribe(backgroundSubscriptionId)
    backgroundSubscriptionId = ''
  }
  if (hmrOverlayTimer !== undefined) {
    window.clearTimeout(hmrOverlayTimer)
    hmrOverlayTimer = undefined
  }
})

const toggleCollapse = () => {
  collapsed.value = !collapsed.value
  localStorage.setItem(SIDER_COLLAPSED_KEY, String(collapsed.value))
}

const isDevelopment = computed(() => {
  return (
    process.env.NODE_ENV === 'development' ||
    import.meta.env.DEV === true ||
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
  const base = (OpenAPI.BASE || 'http://127.0.0.1:36163').replace(/\/+$/, '')
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

const fetchInitialPluginSnapshot = async () => {
  try {
    const response = await authenticatedApiFetch(toBackendUrl('/api/plugins/get'), {
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
    logger.warn(`加载插件页面声明失败，等待实时更新: ${message}`)
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
  const hot = import.meta.hot
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

const mainItems = computed(() =>
  dedupePageDeclarations(declaredPages.value)
    .filter(page => page.visible && page.section === 'main')
    .filter(page => !page.dev_only || isDevelopment.value)
)

const devItems = computed(() =>
  dedupePageDeclarations(declaredPages.value)
    .filter(page => page.visible && page.section === 'dev')
    .filter(page => !page.dev_only || isDevelopment.value)
)

const bottomItems = computed(() =>
  dedupePageDeclarations(declaredPages.value)
    .filter(page => page.visible && page.section === 'bottom')
    .filter(page => !page.dev_only || isDevelopment.value)
)

const allItems = computed(() => [
  ...mainItems.value,
  ...(isDevelopment.value ? devItems.value : []),
  ...bottomItems.value,
])

const selectedKeys = computed(() => {
  const path = route.path
  const exactMatched = allItems.value.find(i => path === i.path)
  if (exactMatched) {
    return [exactMatched.path]
  }

  const prefixMatched = allItems.value
    .filter(i => path.startsWith(i.path))
    .sort((a, b) => b.path.length - a.path.length)[0]

  return [prefixMatched?.path || '/home']
})

const onMenuClick = (path: string) => {
  if (isRouteLocked.value) {
    triggerBlockCallback(path)
    return
  }

  if (route.path !== path) router.push(path)
}

const handleGlobalSearch = (keyword: string) => {
  if (isRouteLocked.value) {
    triggerBlockCallback('/scripts')
    return
  }

  const query = keyword ? { search: keyword } : undefined
  router.push({ path: '/scripts', query })
}

const focusMainContent = () => {
  const main = document.getElementById('app-main-content')
  if (main) {
    main.focus()
    main.scrollIntoView({ block: 'start' })
  }
}
</script>

<style scoped>
.app-layout-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  background: transparent;
  color: var(--v6-color-text);
  font-family: var(--v6-font-sans);
}

.app-window-body {
  position: relative;
  z-index: var(--v6-z-content);
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: transparent;
}

.skip-to-content {
  position: absolute;
  top: -40px;
  left: var(--v6-space-4);
  z-index: var(--v6-z-global-overlay);
  padding: var(--v6-space-2) var(--v6-space-3);
  border-radius: var(--v6-radius-control);
  background: var(--v6-color-info);
  color: var(--v6-color-text-inverse);
  font-size: var(--v6-font-size-sm);
  text-decoration: none;
  transition: top var(--v6-motion-fast) var(--v6-ease-out);
}

.skip-to-content:focus {
  top: var(--v6-space-2);
  outline: none;
  box-shadow: var(--v6-focus-ring);
}

@media (prefers-reduced-motion: reduce) {
  .skip-to-content {
    transition: none;
  }
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
</style>
