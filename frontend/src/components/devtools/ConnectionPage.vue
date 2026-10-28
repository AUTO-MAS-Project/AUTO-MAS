<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, version } from 'vue'
import { useIntervalFn } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { CopyOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { OpenAPI } from '@/api'
import { useWebSocket } from '@/composables/useWebSocket'
import { useAppLifecycle } from '@/composables/useAppLifecycle'
import { useDevtoolsApi } from '@/composables/useDevtoolsApi'
import { subscriptionCount } from '@/services/websocket/subscriptions'
import type { BackendStatus, RuntimeLaunchModeState } from '@/types/electron'
import { copyDevtoolsText } from './helpers'
import { applicationEnvironment } from '@/utils/environment'

const { t } = useI18n()
const appVersion = import.meta.env.VITE_APP_VERSION
const { state, getConnectionInfo } = useWebSocket()
const { manualReconnect } = useAppLifecycle()
const { loading, error, health, latency, probe } = useDevtoolsApi()
const browserHost =
  (window as Window & { __AUTO_MAS_BROWSER_DEV_MODE__?: boolean }).__AUTO_MAS_BROWSER_DEV_MODE__ ===
  true
const connection = ref(getConnectionInfo())
const subscribers = ref(subscriptionCount())
const processStatus = ref<BackendStatus | null>(null)
const runtimeMode = ref<RuntimeLaunchModeState | null>(null)
const statusError = ref('')
const refreshing = ref(false)
const reconnecting = ref(false)
let disposed = false
onUnmounted(() => {
  disposed = true
})

const stateColor = computed(() =>
  state.value === 'open'
    ? 'success'
    : ['connecting', 'reconnecting'].includes(state.value)
      ? 'processing'
      : 'default'
)
const hostLabel = computed(() => (browserHost ? t('core.devtools.browserHost') : 'Electron'))
const modeLabel = computed(() =>
  browserHost
    ? t('core.devtools.externalBackend')
    : (runtimeMode.value?.mode ?? t('core.devtools.unknown'))
)

// 只在概览可见时采样连接层内存状态，不产生额外订阅或 HTTP 请求。
useIntervalFn(() => {
  connection.value = getConnectionInfo()
  subscribers.value = subscriptionCount()
}, 1000)

const refreshStatus = async () => {
  if (refreshing.value || browserHost) return
  refreshing.value = true
  statusError.value = ''
  const results = await Promise.allSettled([
    window.electronAPI.backendStatus(),
    window.electronAPI.getRuntimeLaunchMode(),
  ])
  if (disposed) return
  processStatus.value = results[0].status === 'fulfilled' ? results[0].value : null
  runtimeMode.value = results[1].status === 'fulfilled' ? results[1].value : null
  if (results.some(result => result.status === 'rejected'))
    statusError.value = t('core.devtools.statusFailed')
  refreshing.value = false
}
onMounted(refreshStatus)

const reconnect = async () => {
  if (reconnecting.value) return
  reconnecting.value = true
  try {
    const connected = await manualReconnect()
    if (!disposed)
      message[connected ? 'success' : 'error'](
        t(connected ? 'core.devtools.reconnected' : 'core.devtools.reconnectFailed')
      )
  } catch {
    if (!disposed) message.error(t('core.devtools.reconnectFailed'))
  } finally {
    if (!disposed) reconnecting.value = false
  }
}

const copySummary = () =>
  copyDevtoolsText(
    JSON.stringify(
      {
        appVersion: import.meta.env.VITE_APP_VERSION,
        vueVersion: version,
        host: browserHost ? 'browser' : 'electron',
        applicationEnvironment,
        runtimeMode: runtimeMode.value?.mode ?? null,
        httpApi: OpenAPI.BASE,
        connection: getConnectionInfo(),
        subscribers: subscriptionCount(),
        process: processStatus.value
          ? {
              isRunning: processStatus.value.isRunning,
              pid: processStatus.value.pid,
              runtimeSupervised: processStatus.value.runtimeSupervised,
            }
          : null,
        health: health.value
          ? {
              ready: health.value.ready,
              version: health.value.version,
              protocol: health.value.protocol,
              backgroundStatus: health.value.backgroundStatus,
            }
          : null,
      },
      null,
      2
    )
  )
</script>

<template>
  <div class="connection-summary">
    <div class="summary-cell">
      <span class="devtools-muted">WebSocket</span>
      <a-badge :status="stateColor" :text="state" />
    </div>
    <div class="summary-cell">
      <span class="devtools-muted">{{ t('core.devtools.host') }}</span>
      <strong>{{ hostLabel }}</strong>
    </div>
    <div class="summary-cell">
      <span class="devtools-muted">{{ t('core.devtools.subscriptions') }}</span>
      <strong>{{ subscribers }}</strong>
    </div>
  </div>
  <section class="devtools-section">
    <div class="devtools-toolbar">
      <h3>{{ t('core.devtools.endpoints') }}</h3>
      <a-button size="small" :loading="reconnecting" @click="reconnect">{{
        t('core.devtools.reconnect')
      }}</a-button>
    </div>
    <a-descriptions :column="1" size="small">
      <a-descriptions-item label="HTTP"
        ><code class="devtools-code">{{
          OpenAPI.BASE || t('core.devtools.unknown')
        }}</code></a-descriptions-item
      >
      <a-descriptions-item label="WebSocket"
        ><code class="devtools-code">{{ connection.url || '—' }}</code></a-descriptions-item
      >
      <a-descriptions-item :label="t('core.devtools.reconnectAttempts')">{{
        connection.reconnectAttempts
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('core.devtools.autoReconnect')">{{
        t(connection.automaticReconnectEnabled ? 'core.devtools.enabled' : 'core.devtools.disabled')
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('core.devtools.reconnectScheduled')">{{
        t(connection.hasReconnectTimer ? 'core.devtools.yes' : 'core.devtools.no')
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('core.devtools.preserveBackend')">{{
        t(connection.backendDevMode ? 'core.devtools.yes' : 'core.devtools.no')
      }}</a-descriptions-item>
    </a-descriptions>
  </section>
  <section class="devtools-section">
    <div class="devtools-toolbar">
      <h3>{{ t('core.devtools.runtime') }}</h3>
      <a-button v-if="!browserHost" size="small" :loading="refreshing" @click="refreshStatus"
        ><ReloadOutlined />{{ t('core.devtools.refresh') }}</a-button
      >
    </div>
    <a-alert v-if="statusError" type="warning" :message="statusError" show-icon />
    <a-descriptions :column="2" size="small">
      <a-descriptions-item :label="t('core.devtools.appVersion')">{{
        appVersion
      }}</a-descriptions-item>
      <a-descriptions-item label="Vue">{{ version }}</a-descriptions-item>
      <a-descriptions-item :label="t('core.devtools.applicationEnvironment')">{{
        applicationEnvironment
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('core.devtools.launchMode')">{{
        modeLabel
      }}</a-descriptions-item>
      <a-descriptions-item
        v-if="processStatus?.pid"
        :label="processStatus.runtimeSupervised ? t('core.devtools.supervisorPid') : 'PID'"
        >{{ processStatus.pid }}</a-descriptions-item
      >
    </a-descriptions>
    <p class="devtools-muted">{{ t('core.devtools.processHint') }}</p>
  </section>
  <section class="devtools-section">
    <div class="devtools-toolbar">
      <h3>{{ t('core.devtools.health') }}</h3>
      <a-button size="small" :loading="loading" @click="probe">{{
        t('core.devtools.probe')
      }}</a-button>
    </div>
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <a-descriptions v-else-if="health" :column="2" size="small">
      <a-descriptions-item :label="t('core.devtools.readiness')"
        ><a-badge
          :status="health.ready ? 'success' : 'warning'"
          :text="t(health.ready ? 'core.devtools.ready' : 'core.devtools.notReady')"
      /></a-descriptions-item>
      <a-descriptions-item :label="t('core.devtools.latency')"
        >{{ latency }} ms</a-descriptions-item
      >
      <a-descriptions-item :label="t('core.devtools.backendVersion')">{{
        health.version
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('core.devtools.backgroundStatus')">{{
        health.backgroundStatus
      }}</a-descriptions-item>
    </a-descriptions>
    <p v-else class="devtools-muted">{{ t('core.devtools.probeHint') }}</p>
  </section>
  <div class="devtools-toolbar">
    <span class="devtools-muted">{{ t('core.devtools.summaryHint') }}</span>
    <a-button @click="copySummary"><CopyOutlined />{{ t('core.devtools.copySummary') }}</a-button>
  </div>
</template>

<style scoped>
.connection-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.summary-cell {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}
.summary-cell strong {
  font-size: 16px;
  font-weight: 600;
}
@media (max-width: 480px) {
  .connection-summary {
    grid-template-columns: 1fr;
  }
}
</style>
