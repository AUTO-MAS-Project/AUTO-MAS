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
            @press-enter="submitManualInstall"
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
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_ID_PLUGIN_MARKET,
  WS_MARKET_ERROR,
  WS_MARKET_SNAPSHOT_REQUEST,
  WS_MARKET_SNAPSHOT_RESPONSE,
  WS_PLUGIN_INSTALL_PROGRESS,
  WS_PLUGIN_INSTALL_REQUEST,
  WS_PLUGIN_INSTALL_RESULT,
  WS_PLUGIN_INSTALLED_SYNC,
  WS_PLUGIN_UNINSTALL_REQUEST,
  WS_PLUGIN_UNINSTALL_RESULT,
} from '@/services/websocket/types'

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

interface PluginMarketMessageData {
  requestId?: string
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

const { state, subscribe, unsubscribe, send, request } = useWebSocket()

const isConnected = computed(() => state.value === 'open')
const wsStatus = computed(() => {
  switch (state.value) {
    case 'open':
      return '已连接'
    case 'connecting':
    case 'reconnecting':
      return '连接中'
    case 'closed':
      return '已断开'
    default:
      return '未连接'
  }
})

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

const subscriptionIds: string[] = []

const normalizeName = (name: string) =>
  String(name || '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_')

const setInfo = (msg: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') => {
  lastInfoType.value = type
  lastInfoMessage.value = msg
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

const newRequestId = () => `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

const sendPluginRequest = (type: string, payload: Record<string, unknown> = {}): boolean => {
  const sent = send(WS_ID_PLUGIN_MARKET, type, {
    requestId: newRequestId(),
    ...payload,
  })
  if (!sent) {
    message.warning('插件市场 WS 未连接')
  }
  return sent
}

const requestSnapshot = async () => {
  if (snapshotLoading.value) {
    return
  }
  snapshotLoading.value = true
  try {
    const response = await request(
      WS_ID_PLUGIN_MARKET,
      WS_MARKET_SNAPSHOT_REQUEST,
      [WS_MARKET_SNAPSHOT_RESPONSE, WS_MARKET_ERROR],
      { perPrefixLimit: 60 },
      15000
    )
    if (response.type === WS_MARKET_ERROR) {
      // 错误提示由 market.error 订阅统一展示
      return
    }
    const data = response.data as PluginMarketMessageData
    applySnapshot((data.payload || {}) as MarketSnapshot)
    if (marketSnapshot.value) {
      saveSnapshotCache(marketSnapshot.value)
    }
    setInfo('市场快照已更新', 'success')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`获取市场快照失败: ${errorMsg}`)
    setInfo(`获取市场快照失败: ${errorMsg}`, 'error')
  } finally {
    snapshotLoading.value = false
  }
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
  if (!sendPluginRequest(WS_PLUGIN_INSTALL_REQUEST, { package: packageName })) {
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
    if (!sendPluginRequest(WS_PLUGIN_UNINSTALL_REQUEST, { package: pkg })) {
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

const handleInstallProgress = (data: PluginMarketMessageData) => {
  const payload = data.payload || {}
  const pkg = String(payload.package || '')
  const progress = Number(payload.progress || 0)
  if (pkg) {
    setInfo(`安装中: ${pkg} (${progress}%)`, 'info')
  }
}

const handleInstallResult = (data: PluginMarketMessageData) => {
  const payload = data.payload || {}
  const status = String(data.status || 'success')
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
  setInfo(data.message || (ok ? '安装成功' : '安装失败'), ok ? 'success' : 'error')
  if (ok) {
    message.success(data.message || '安装成功')
  } else {
    message.error(data.message || '安装失败')
  }
}

const handleUninstallResult = (data: PluginMarketMessageData) => {
  const payload = data.payload || {}
  const status = String(data.status || 'success')
  const pkg = String(payload.package || '')
  if (pkg) {
    markOperation(pkg, false)
  }
  const ok = status !== 'error' && Boolean(payload.success)
  if (ok && pkg) {
    updateInstalledState(pkg, false)
  }
  setInfo(data.message || (ok ? '卸载成功' : '卸载失败'), ok ? 'success' : 'error')
  if (ok) {
    message.success(data.message || '卸载成功')
  } else {
    message.error(data.message || '卸载失败')
  }
}

const handleInstalledSync = (data: PluginMarketMessageData) => {
  const payload = data.payload || {}
  const pkg = String(payload.package || '')
  if (!pkg) {
    return
  }
  updateInstalledState(pkg, Boolean(payload.installed))
  markOperation(pkg, false)
}

const handleMarketError = (data: PluginMarketMessageData) => {
  snapshotLoading.value = false
  const msg = data.message || '插件通道发生错误'
  setInfo(msg, 'error')
  message.error(msg)
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
      String(item.package || '')
        .toLowerCase()
        .includes(keyword) ||
      String(item.summary || '')
        .toLowerCase()
        .includes(keyword)
    )
  })
})

onMounted(() => {
  subscriptionIds.push(
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_INSTALL_PROGRESS }, msg =>
      handleInstallProgress(msg.data as PluginMarketMessageData)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_INSTALL_RESULT }, msg =>
      handleInstallResult(msg.data as PluginMarketMessageData)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_UNINSTALL_RESULT }, msg =>
      handleUninstallResult(msg.data as PluginMarketMessageData)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_INSTALLED_SYNC }, msg =>
      handleInstalledSync(msg.data as PluginMarketMessageData)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_MARKET_ERROR }, msg =>
      handleMarketError(msg.data as PluginMarketMessageData)
    )
  )

  const cachedSnapshot = loadSnapshotCache()
  if (cachedSnapshot) {
    applySnapshot(cachedSnapshot)
    setInfo('已加载本地缓存，点击“刷新快照”可获取最新市场数据', 'info')
  } else {
    void requestSnapshot()
  }
})

onUnmounted(() => {
  subscriptionIds.forEach(id => unsubscribe(id))
  subscriptionIds.length = 0
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
