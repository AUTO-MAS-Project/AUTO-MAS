<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { useEventListener, useWindowSize } from '@vueuse/core'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BugOutlined, CloseOutlined } from '@ant-design/icons-vue'
import { useWebSocket } from '@/composables/useWebSocket'
import ConnectionPage from './ConnectionPage.vue'
import StoragePage from './StoragePage.vue'
import RoutesPage from './RoutesPage.vue'
import ToolsPage from './ToolsPage.vue'
import type { RouteVisit } from './types'
import { cancelVueInspection } from './vueDevtools'
import './devtools.css'

defineOptions({ name: 'DevtoolsPanel' })

const { t } = useI18n()
const router = useRouter()
const { state } = useWebSocket()
const { width } = useWindowSize()
const open = ref(false)
const activeTab = ref('connection')
const storagePage = ref<InstanceType<typeof StoragePage> | null>(null)
const history = ref<RouteVisit[]>([])
const panelWidth = computed(() => Math.min(780, Math.max(280, width.value - 24)))
const tabs = computed(() => [
  { key: 'connection', label: t('devtools.connection') },
  { key: 'storage', label: t('devtools.storage') },
  { key: 'routes', label: t('devtools.routes') },
  { key: 'tools', label: t('devtools.tools') },
])

// 历史属于面板会话，切换标签、关闭工作台都不丢失；不持久化路由参数。
const recordVisit = (fullPath: string) => {
  history.value.unshift({ fullPath, time: new Date().toLocaleTimeString() })
  history.value = history.value.slice(0, 30)
}
recordVisit(router.currentRoute.value.fullPath)
const stopHistory = router.afterEach((to, _from, failure) => {
  if (!failure) recordVisit(to.fullPath)
})
onUnmounted(() => {
  stopHistory()
  cancelVueInspection()
})

const canLeave = async () => (await storagePage.value?.canLeave()) ?? true

const closePanel = async () => {
  if (await canLeave()) open.value = false
}

const changeTab = async (key: string | number) => {
  if (await canLeave()) activeTab.value = String(key)
}

useEventListener(document, 'keydown', (event: KeyboardEvent) => {
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.code === 'KeyD') {
    event.preventDefault()
    if (event.repeat) return
    cancelVueInspection()
    if (open.value) void closePanel()
    else open.value = true
  }
  if (event.code === 'Escape' && cancelVueInspection()) return
  if (event.code === 'Escape' && open.value) {
    const modalVisible = Array.from(document.querySelectorAll('.ant-modal-wrap')).some(
      element => element.getClientRects().length > 0
    )
    if (modalVisible) return
    event.preventDefault()
    void closePanel()
  }
})
</script>

<template>
  <a-button
    v-if="!open"
    class="devtools-launcher"
    :aria-label="t('devtools.open')"
    @click="open = true"
  >
    <BugOutlined />
    <span>DEV</span>
    <span class="devtools-connection-dot" :class="{ connected: state === 'open' }" />
  </a-button>
  <a-drawer
    :open="open"
    :width="panelWidth"
    :mask="false"
    :closable="false"
    :keyboard="false"
    :destroy-on-close="true"
    root-class-name="mas-devtools"
    @close="closePanel"
  >
    <template #title>
      <div class="devtools-heading">
        <BugOutlined />
        <div>
          <strong>{{ t('devtools.title') }}</strong>
          <span class="devtools-caption">{{ t('devtools.subtitle') }}</span>
        </div>
      </div>
    </template>
    <template #extra>
      <a-space>
        <kbd class="devtools-shortcut">Ctrl ⇧ D</kbd>
        <a-button type="text" :aria-label="t('devtools.close')" @click="closePanel">
          <CloseOutlined />
        </a-button>
      </a-space>
    </template>
    <a-tabs :active-key="activeTab" @change="changeTab">
      <a-tab-pane v-for="tab in tabs" :key="tab.key" :tab="tab.label" />
    </a-tabs>
    <main v-if="open" class="devtools-page">
      <ConnectionPage v-if="activeTab === 'connection'" />
      <StoragePage v-else-if="activeTab === 'storage'" ref="storagePage" />
      <RoutesPage v-else-if="activeTab === 'routes'" :history="history" />
      <ToolsPage v-else @inspect="closePanel" />
    </main>
  </a-drawer>
</template>

<style scoped>
.devtools-launcher {
  position: fixed;
  inset: auto 20px 20px auto;
  z-index: 990;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  box-shadow: var(--ant-box-shadow-secondary);
  font-family: var(--font-monospace);
}

.devtools-connection-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-text-tertiary);
}

.devtools-connection-dot.connected {
  background: var(--ant-color-success);
}
</style>
