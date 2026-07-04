<template>
  <div class="plugin-market-page">
    <div class="market-header">
      <div class="title-wrap">
        <h1 class="title">插件市场</h1>
        <a-tag :color="isConnected ? 'success' : 'default'">{{ wsStatus }}</a-tag>
      </div>
      <a-space>
        <a-input
          v-model:value="searchKeyword"
          allow-clear
          placeholder="搜索包名或简介（本地过滤）"
          style="width: 280px"
        />
        <a-button :loading="snapshotLoading" @click="requestSnapshot">刷新快照</a-button>
        <a-button @click="openManualInstall">手动安装</a-button>
      </a-space>
    </div>

    <a-alert
      v-if="lastInfoMessage"
      style="margin-bottom: 12px"
      :type="lastInfoType"
      show-icon
      :message="lastInfoMessage"
    />

    <a-empty v-if="!marketSnapshot" description="尚未获取市场快照，请点击“刷新快照”" />

    <template v-else>
      <div class="snapshot-meta">
        <a-space>
          <a-tag color="processing">共 {{ marketSnapshot.total }} 个包</a-tag>
          <a-tag>更新时间: {{ formatTime(marketSnapshot.fetched_at) }}</a-tag>
        </a-space>
      </div>

      <a-empty v-if="filteredItems.length === 0" description="没有匹配项" />

      <div v-else class="card-grid">
        <a-card
          v-for="item in filteredItems"
          :key="item.package"
          class="plugin-card"
          :bordered="false"
          @click="goToPackage(item.project_url)"
        >
          <template #title>
            <div class="card-title">
              <span class="name">{{ item.package }}</span>
              <a-tag color="blue">{{ item.version || 'unknown' }}</a-tag>
            </div>
          </template>

          <div class="summary">{{ item.summary || '暂无简介' }}</div>

          <div class="card-actions">
            <a-space>
              <a-button
                type="primary"
                :danger="isInstalled(item.package)"
                :loading="isOperationLoading(item.package)"
                @click.stop="toggleInstall(item.package)"
              >
                {{ isInstalled(item.package) ? '卸载' : '安装' }}
              </a-button>
            </a-space>
          </div>
        </a-card>
      </div>
    </template>

    <a-modal
      v-model:open="manualInstallVisible"
      title="手动安装插件包"
      :mask-closable="!manualInstallSubmitting"
      :keyboard="!manualInstallSubmitting"
      :closable="!manualInstallSubmitting"
      @cancel="closeManualInstall"
    >
      <a-form layout="vertical">
        <a-form-item label="PyPI 包名">
          <a-input
            v-model:value="manualPackageName"
            allow-clear
            placeholder="例如：automas_xxx"
            :disabled="manualInstallSubmitting"
            @pressEnter="submitManualInstall"
          />
        </a-form-item>
      </a-form>
      <a-alert
        type="info"
        show-icon
        message="输入精确包名后，将直接从 PyPI 下载并安装到当前插件目录。"
      />
      <template #footer>
        <a-space>
          <a-button :disabled="manualInstallSubmitting" @click="closeManualInstall">取消</a-button>
          <a-button type="primary" :loading="manualInstallSubmitting" @click="submitManualInstall">
            开始安装
          </a-button>
        </a-space>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { OpenAPI } from '@/api'

interface MarketItem {
  package: string
  version: string
  summary: string
  project_url: string
  prefix_tag: string
}

interface MarketSnapshot {
  schema_version: number
  prefix_tags: string[]
  fetched_at: string
  items: MarketItem[]
  installed_map: Record<string, boolean>
  total: number
}

interface PluginMessageEnvelope {
  event?: string
  request_id?: string | null
  status?: string
  message?: string
  payload?: any
}

interface PluginMarketCache {
  snapshot: MarketSnapshot
  saved_at: string
}

const logger = window.electronAPI.getLogger('插件市场')
const PLUGIN_MARKET_CACHE_KEY = 'auto-mas-plugin-market-cache-v1'
const wsStatus = ref('未连接')
const isConnected = ref(false)
const wsRef = ref<WebSocket | null>(null)
const reconnectTimer = ref<number | null>(null)
const manualClose = ref(false)
const shouldFetchOnConnect = ref(false)

const marketSnapshot = ref<MarketSnapshot | null>(null)
const installedState = ref<Record<string, boolean>>({})
const operationLoading = ref<Record<string, boolean>>({})
const searchKeyword = ref('')
const snapshotLoading = ref(false)
const manualInstallVisible = ref(false)
const manualPackageName = ref('')
const pendingManualPackage = ref('')

const lastInfoType = ref<'success' | 'error' | 'info' | 'warning'>('info')
const lastInfoMessage = ref('')

const normalizeName = (name: string) => String(name || '').trim().toLowerCase().replace(/-/g, '_')

const setInfo = (msg: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') => {
  lastInfoType.value = type
  lastInfoMessage.value = msg
}

const buildWsUrl = (): string => {
  const base = (OpenAPI.BASE || '').trim()
  if (base.startsWith('https://')) {
    return `${base.replace('https://', 'wss://')}/api/ws/plugin`
  }
  if (base.startsWith('http://')) {
    return `${base.replace('http://', 'ws://')}/api/ws/plugin`
  }
  if (base.startsWith('wss://') || base.startsWith('ws://')) {
    return `${base}/api/ws/plugin`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}/api/ws/plugin`
}

const applySnapshot = (snapshot: MarketSnapshot) => {
  marketSnapshot.value = snapshot
  const nextState: Record<string, boolean> = {}
  Object.entries(snapshot.installed_map || {}).forEach(([pkg, installed]) => {
    nextState[normalizeName(pkg)] = Boolean(installed)
  })
  installedState.value = nextState
}

const saveSnapshotCache = (snapshot: MarketSnapshot) => {
  try {
    const payload: PluginMarketCache = {
      snapshot,
      saved_at: new Date().toISOString(),
    }
    sessionStorage.setItem(PLUGIN_MARKET_CACHE_KEY, JSON.stringify(payload))
  } catch (error) {
    logger.warn(`写入插件市场缓存失败: ${String(error)}`)
  }
}

const loadSnapshotCache = (): MarketSnapshot | null => {
  try {
    const raw = sessionStorage.getItem(PLUGIN_MARKET_CACHE_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as PluginMarketCache
    if (!parsed || typeof parsed !== 'object' || !parsed.snapshot) {
      return null
    }
    return parsed.snapshot
  } catch (error) {
    logger.warn(`读取插件市场缓存失败: ${String(error)}`)
    return null
  }
}

const updateInstalledState = (pkg: string, installed: boolean) => {
  const normalized = normalizeName(pkg)
  installedState.value = {
    ...installedState.value,
    [normalized]: installed,
  }

  if (marketSnapshot.value) {
    marketSnapshot.value = {
      ...marketSnapshot.value,
      installed_map: {
        ...marketSnapshot.value.installed_map,
        [pkg]: installed,
      },
    }
    saveSnapshotCache(marketSnapshot.value)
  }
}

const clearReconnectTimer = () => {
  if (reconnectTimer.value !== null) {
    window.clearTimeout(reconnectTimer.value)
    reconnectTimer.value = null
  }
}

const sendPluginAction = (action: string, payload: Record<string, unknown> = {}): boolean => {
  const ws = wsRef.value
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    message.warning('插件市场 WS 未连接')
    return false
  }

  ws.send(
    JSON.stringify({
      action,
      request_id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      payload,
    })
  )
  return true
}

const requestSnapshot = () => {
  if (!sendPluginAction('market.snapshot.request', { per_prefix_limit: 60 })) {
    snapshotLoading.value = false
    return
  }
  snapshotLoading.value = true
}

const isInstalled = (pkg: string) => Boolean(installedState.value[normalizeName(pkg)])

const isOperationLoading = (pkg: string) => Boolean(operationLoading.value[normalizeName(pkg)])

const manualInstallSubmitting = computed(() => {
  const pkg = manualPackageName.value.trim()
  if (!pkg) {
    return false
  }
  return isOperationLoading(pkg)
})

const markOperation = (pkg: string, loading: boolean) => {
  operationLoading.value = {
    ...operationLoading.value,
    [normalizeName(pkg)]: loading,
  }
}

const requestInstall = (pkg: string): boolean => {
  const packageName = String(pkg || '').trim()
  if (!packageName) {
    message.warning('请先输入包名')
    return false
  }
  if (isOperationLoading(packageName)) {
    return false
  }
  markOperation(packageName, true)
  if (!sendPluginAction('plugin.install.request', { package: packageName })) {
    markOperation(packageName, false)
    return false
  }
  return true
}

const toggleInstall = (pkg: string) => {
  if (isOperationLoading(pkg)) {
    return
  }

  markOperation(pkg, true)
  if (isInstalled(pkg)) {
    if (!sendPluginAction('plugin.uninstall.request', { package: pkg })) {
      markOperation(pkg, false)
    }
  } else {
    requestInstall(pkg)
  }
}

const openManualInstall = () => {
  manualInstallVisible.value = true
}

const closeManualInstall = () => {
  if (manualInstallSubmitting.value) {
    return
  }
  manualInstallVisible.value = false
}

const submitManualInstall = () => {
  const packageName = manualPackageName.value.trim()
  if (!packageName) {
    message.warning('请输入要安装的包名')
    return
  }
  pendingManualPackage.value = normalizeName(packageName)
  if (!requestInstall(packageName)) {
    pendingManualPackage.value = ''
    return
  }
  setInfo(`已发起手动安装请求: ${packageName}`, 'info')
}

const goToPackage = (url: string) => {
  const target = String(url || '').trim()
  if (!target) {
    return
  }
  window.open(target, '_blank', 'noopener,noreferrer')
}

const onPluginMessage = (envelope: PluginMessageEnvelope) => {
  const event = String(envelope.event || '')
  const status = String(envelope.status || 'success')
  const payload = envelope.payload || {}

  if (event === 'market.snapshot.response') {
    snapshotLoading.value = false
    applySnapshot(payload as MarketSnapshot)
    if (marketSnapshot.value) {
      saveSnapshotCache(marketSnapshot.value)
    }
    shouldFetchOnConnect.value = false
    setInfo('市场快照已更新', 'success')
    return
  }

  if (event === 'plugin.install.progress') {
    const pkg = String(payload.package || '')
    const progress = Number(payload.progress || 0)
    if (pkg) {
      setInfo(`安装中: ${pkg} (${progress}%)`, 'info')
    }
    return
  }

  if (event === 'plugin.install.result') {
    const pkg = String(payload.package || '')
    if (pkg) {
      markOperation(pkg, false)
    }
    const ok = status !== 'error' && Boolean(payload.success)
    if (ok && pkg) {
      updateInstalledState(pkg, true)
    }
    if (pkg && normalizeName(pkg) === pendingManualPackage.value) {
      if (ok) {
        manualPackageName.value = ''
        manualInstallVisible.value = false
      }
      pendingManualPackage.value = ''
    }
    setInfo(envelope.message || (ok ? '安装成功' : '安装失败'), ok ? 'success' : 'error')
    if (ok) {
      message.success(envelope.message || '安装成功')
    } else {
      message.error(envelope.message || '安装失败')
    }
    return
  }

  if (event === 'plugin.uninstall.result') {
    const pkg = String(payload.package || '')
    if (pkg) {
      markOperation(pkg, false)
    }
    const ok = status !== 'error' && Boolean(payload.success)
    if (ok && pkg) {
      updateInstalledState(pkg, false)
    }
    setInfo(envelope.message || (ok ? '卸载成功' : '卸载失败'), ok ? 'success' : 'error')
    if (ok) {
      message.success(envelope.message || '卸载成功')
    } else {
      message.error(envelope.message || '卸载失败')
    }
    return
  }

  if (event === 'plugin.installed.sync') {
    const pkg = String(payload.package || '')
    if (!pkg) {
      return
    }
    updateInstalledState(pkg, Boolean(payload.installed))
    markOperation(pkg, false)
    return
  }

  if (event === 'plugin.error') {
    snapshotLoading.value = false
    const msg = envelope.message || '插件通道发生错误'
    setInfo(msg, 'error')
    message.error(msg)
    return
  }

  if (event === 'plugin.channel.ready') {
    setInfo('插件通道已就绪，可手动刷新快照', 'info')
  }
}

const connectWs = () => {
  clearReconnectTimer()
  const wsUrl = buildWsUrl()
  const ws = new WebSocket(wsUrl)
  wsRef.value = ws
  wsStatus.value = '连接中'

  ws.onopen = () => {
    isConnected.value = true
    wsStatus.value = '已连接'
    logger.info(`插件市场 WS 已连接: ${wsUrl}`)
    if (shouldFetchOnConnect.value || !marketSnapshot.value) {
      requestSnapshot()
      shouldFetchOnConnect.value = false
    }
  }

  ws.onmessage = event => {
    try {
      const raw = JSON.parse(String(event.data || '{}'))

      if (raw?.type === 'Signal' && raw?.data?.Ping) {
        ws.send(JSON.stringify({ id: 'Client', type: 'Signal', data: { Pong: 'heartbeat' } }))
        return
      }

      const data = raw?.data
      if (raw?.type !== 'Message' || !data || typeof data !== 'object') {
        return
      }
      onPluginMessage(data as PluginMessageEnvelope)
    } catch (error) {
      logger.error(`插件市场消息解析失败: ${String(error)}`)
    }
  }

  ws.onerror = error => {
    wsStatus.value = '连接错误'
    logger.error(`插件市场 WS 错误: ${String(error)}`)
  }

  ws.onclose = () => {
    isConnected.value = false
    wsStatus.value = '已断开'
    wsRef.value = null
    logger.info('插件市场 WS 已断开')

    if (!manualClose.value) {
      reconnectTimer.value = window.setTimeout(() => {
        connectWs()
      }, 1500)
    }
  }
}

const formatTime = (ts: string) => {
  const parsed = Date.parse(ts || '')
  if (Number.isNaN(parsed)) {
    return ts || '-'
  }
  return new Date(parsed).toLocaleString()
}

const filteredItems = computed(() => {
  const snapshot = marketSnapshot.value
  if (!snapshot) {
    return []
  }
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) {
    return snapshot.items
  }
  return snapshot.items.filter(item => {
    return (
      String(item.package || '').toLowerCase().includes(keyword) ||
      String(item.summary || '').toLowerCase().includes(keyword)
    )
  })
})

onMounted(() => {
  manualClose.value = false
  const cachedSnapshot = loadSnapshotCache()
  if (cachedSnapshot) {
    applySnapshot(cachedSnapshot)
    setInfo('已加载本地缓存，点击“刷新快照”可获取最新市场数据', 'info')
    shouldFetchOnConnect.value = false
  } else {
    shouldFetchOnConnect.value = true
  }
  connectWs()
})

onUnmounted(() => {
  manualClose.value = true
  clearReconnectTimer()
  const ws = wsRef.value
  wsRef.value = null
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close()
  }
})
</script>

<style scoped>
.plugin-market-page {
  height: 100%;
  padding: 16px;
  overflow: auto;
}

.market-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
  flex-wrap: wrap;
}

.title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.snapshot-meta {
  margin-bottom: 12px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.plugin-card {
  border-radius: 12px;
  min-height: 188px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  cursor: pointer;
}

.plugin-card :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title .name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
}

.summary {
  color: var(--ant-color-text-secondary);
  min-height: 56px;
  line-height: 1.5;
}

.card-actions {
  margin-top: 6px;
}
</style>
