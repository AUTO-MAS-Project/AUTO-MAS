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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { pluginMarketApi, type PluginMarketSnapshot } from '@/services/pluginMarketApi'
import {
  buildMarketSnapshotState,
  PluginOperationRequestTracker,
  SnapshotRefreshCoordinator,
  startPluginInstall,
} from './PluginMarket.logic'
import {
  WS_ID_PLUGIN_MARKET,
  WS_MARKET_ERROR,
  WS_PLUGIN_INSTALL_PROGRESS,
  WS_PLUGIN_INSTALL_REQUEST,
  WS_PLUGIN_INSTALL_RESULT,
  WS_PLUGIN_INSTALLED_SYNC,
  WS_PLUGIN_UNINSTALL_REQUEST,
  WS_PLUGIN_UNINSTALL_RESULT,
  type WSMarketErrorData,
  type WSPluginInstalledSyncData,
  type WSPluginInstallProgressData,
  type WSPluginOperationResultData,
  type WSJsonObject,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('插件市场')

const { state, subscribe, unsubscribe, send } = useWebSocket()

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

const marketSnapshot = ref<PluginMarketSnapshot | null>(null)
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
let stopConnectionWatch: (() => void) | null = null
const snapshotCoordinator = new SnapshotRefreshCoordinator<PluginMarketSnapshot>()

const normalizeName = (name: string) =>
  String(name || '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_')

const operationRequests = new PluginOperationRequestTracker(normalizeName)

const setInfo = (msg: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') => {
  lastInfoType.value = type
  lastInfoMessage.value = msg
}

const applySnapshot = (snapshot: PluginMarketSnapshot) => {
  const nextState = buildMarketSnapshotState(snapshot, normalizeName)
  marketSnapshot.value = nextState.snapshot
  installedState.value = nextState.installedState
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
  }
}

const newRequestId = () => `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

const sendPluginRequest = (type: string, payload: WSJsonObject = {}): string | null => {
  const requestId = newRequestId()
  const sent = send(WS_ID_PLUGIN_MARKET, type, {
    ...payload,
    requestId,
  })
  if (!sent) {
    message.warning('插件市场 WS 未连接')
    return null
  }
  return requestId
}

const requestSnapshot = () => {
  snapshotCoordinator.refresh({
    load: () => pluginMarketApi.getSnapshot(60),
    apply: snapshot => {
      applySnapshot(snapshot)
      setInfo('市场快照已更新', 'success')
    },
    reportError: error => {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`获取市场快照失败: ${errorMsg}`)
      setInfo(`获取市场快照失败: ${errorMsg}`, 'error')
    },
    setLoading: loading => {
      snapshotLoading.value = loading
    },
  })
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
  return startPluginInstall(packageName, isOperationLoading, markOperation, pluginPackage => {
    const requestId = sendPluginRequest(WS_PLUGIN_INSTALL_REQUEST, { package: pluginPackage })
    if (!requestId) return false
    operationRequests.begin('install', pluginPackage, requestId)
    return true
  })
}

const toggleInstall = (pkg: string) => {
  if (isOperationLoading(pkg)) {
    return
  }

  if (isInstalled(pkg)) {
    markOperation(pkg, true)
    const requestId = sendPluginRequest(WS_PLUGIN_UNINSTALL_REQUEST, { package: pkg })
    if (!requestId) {
      markOperation(pkg, false)
    } else {
      operationRequests.begin('uninstall', pkg, requestId)
    }
  } else {
    // requestInstall 负责设置安装态；提前标记会使它因 loading 而短路。
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

const handleInstallProgress = (data: WSPluginInstallProgressData) => {
  const pkg = data.package
  if (!operationRequests.matches('install', pkg, data.requestId)) return
  const progress = data.progress
  if (pkg) {
    setInfo(`安装中: ${pkg} (${progress}%)`, 'info')
  }
}

const handleInstallResult = (data: WSPluginOperationResultData) => {
  const status = data.status
  const pkg = data.package
  if (!operationRequests.finish('install', pkg, data.requestId)) return
  snapshotCoordinator.invalidate()
  if (pkg) {
    markOperation(pkg, false)
  }
  const ok = status !== 'error' && data.success
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

const handleUninstallResult = (data: WSPluginOperationResultData) => {
  const status = data.status
  const pkg = data.package
  if (!operationRequests.finish('uninstall', pkg, data.requestId)) return
  snapshotCoordinator.invalidate()
  if (pkg) {
    markOperation(pkg, false)
  }
  const ok = status !== 'error' && data.success
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

const handleInstalledSync = (data: WSPluginInstalledSyncData) => {
  snapshotCoordinator.invalidate()
  const pkg = data.package
  if (!pkg) {
    return
  }
  updateInstalledState(pkg, data.installed)
}

const handleMarketError = (data: WSMarketErrorData) => {
  const pending = operationRequests.finishByRequestId(data.requestId)
  if (data.requestId && !pending) return
  if (pending) {
    markOperation(pending.package, false)
    if (pending.operation === 'install' && pending.package === pendingManualPackage.value) {
      pendingManualPackage.value = ''
    }
  }
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
  const items = snapshot.items ?? []
  if (!keyword) {
    return items
  }
  return items.filter(item => {
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
      handleInstallProgress(msg.data)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_INSTALL_RESULT }, msg =>
      handleInstallResult(msg.data)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_UNINSTALL_RESULT }, msg =>
      handleUninstallResult(msg.data)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_INSTALLED_SYNC }, msg =>
      handleInstalledSync(msg.data)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_MARKET_ERROR }, msg =>
      handleMarketError(msg.data)
    )
  )

  // 先注册实时订阅，再经 HTTP 获取初始快照，避免 HTTP 请求期间漏掉后续事件。
  stopConnectionWatch = watch(state, (nextState, previousState) => {
    if (nextState === 'open' && previousState !== 'open') requestSnapshot()
  })
  requestSnapshot()
})

onUnmounted(() => {
  operationRequests.clear()
  subscriptionIds.forEach(id => unsubscribe(id))
  subscriptionIds.length = 0
  stopConnectionWatch?.()
  stopConnectionWatch = null
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
