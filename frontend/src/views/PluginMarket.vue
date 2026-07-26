<template>
  <div class="plugin-market-page">
    <PluginErrorBoundary extension-id="plugin-market" plugin-name="插件市场">
      <main class="market-shell">
        <header class="market-header">
          <!-- 统一 MacPageHeader 规范（compact + transparent） -->
          <MacPageHeader
            class="market-heading"
            title="插件市场"
            subtitle="发现、安装与维护 AUTO-MAS 扩展"
            compact
            transparent
          />
          <div class="market-tabs" role="tablist" aria-label="市场分类">
            <button
              type="button"
              role="tab"
              :class="{ 'is-active': marketTab === 'recommended' }"
              :aria-selected="marketTab === 'recommended'"
              @click="selectMarketTab('recommended')"
            >
              推荐
            </button>
            <button
              type="button"
              role="tab"
              :class="{ 'is-active': marketTab === 'all' }"
              :aria-selected="marketTab === 'all'"
              @click="selectMarketTab('all')"
            >
              全部
            </button>
            <button
              type="button"
              role="tab"
              :class="{ 'is-active': marketTab === 'installed' }"
              :aria-selected="marketTab === 'installed'"
              @click="selectMarketTab('installed')"
            >
              已安装
            </button>
          </div>
          <div
            class="connection-pill"
            :class="{ 'connection-pill--online': isConnected }"
            role="status"
          >
            <span class="connection-dot" aria-hidden="true"></span>
            <span>
              <strong>{{ wsStatus }}</strong>
              <small>{{ connectionHint }}</small>
            </span>
          </div>
        </header>

        <div class="market-toolbar" aria-label="插件市场工具栏">
          <a-input
            v-model:value="searchKeyword"
            class="market-search"
            allow-clear
            placeholder="搜索插件"
            @update:value="marketTab = 'all'"
          />
          <a-select
            v-model:value="installFilter"
            class="market-filter"
            aria-label="安装状态筛选"
            :options="installFilterOptions"
            @update:value="syncMarketTabFromInstallFilter"
          />
          <a-select
            v-if="prefixFilterOptions.length > 1"
            v-model:value="prefixFilter"
            class="market-filter market-filter--prefix"
            aria-label="包名前缀筛选"
            :options="prefixFilterOptions"
            @update:value="marketTab = 'all'"
          />
          <div class="toolbar-actions">
            <a-button
              :loading="snapshotLoading"
              :disabled="!isConnected"
              @click="requestSnapshot()"
            >
              刷新
            </a-button>
            <a-button type="primary" :disabled="!isConnected" @click="openManualInstall">
              手动安装
            </a-button>
          </div>
        </div>

        <div
          v-if="lastInfoMessage"
          class="market-feedback"
          :class="`market-feedback--${lastInfoType}`"
          role="status"
        >
          {{ lastInfoMessage }}
        </div>

        <div v-if="marketSnapshot" class="snapshot-bar" aria-label="市场快照信息">
          <div>
            <strong>{{ filteredItems.length }}</strong>
            <span> / {{ marketSnapshot.total }} 个包</span>
          </div>
          <div class="snapshot-source">
            <span>PyPI 仓库</span>
            <span aria-hidden="true">·</span>
            <span>{{ formatTime(marketSnapshot.fetched_at) }}</span>
            <span v-if="!isConnected" class="offline-label">离线缓存</span>
          </div>
        </div>

        <section class="market-content" aria-label="可用插件">
          <div class="market-scroll">
            <LoadingSkeleton
              v-if="snapshotLoading && !marketSnapshot"
              class="market-loading"
              variant="list"
              :rows="4"
            />

            <StatePanel
              v-else-if="marketLoadError && !marketSnapshot"
              type="error"
              title="插件市场加载失败"
            >
              <p class="state-description">{{ marketLoadError }}</p>
              <template #actions>
                <a-button
                  type="primary"
                  size="small"
                  :disabled="!isConnected"
                  @click="requestSnapshot()"
                >
                  重新加载
                </a-button>
              </template>
            </StatePanel>

            <StatePanel v-else-if="!marketSnapshot" type="neutral" title="尚未获取市场快照">
              <p class="state-description">连接后刷新快照，即可浏览可安装的插件包。</p>
              <template #actions>
                <a-button
                  type="primary"
                  size="small"
                  :disabled="!isConnected"
                  @click="requestSnapshot()"
                >
                  刷新快照
                </a-button>
              </template>
            </StatePanel>

            <StatePanel
              v-else-if="filteredItems.length === 0"
              type="neutral"
              title="没有匹配的插件"
            >
              <p class="state-description">请调整搜索或筛选条件后重试。</p>
              <template v-if="hasActiveFilters" #actions>
                <a-button size="small" @click="clearFilters">清除筛选</a-button>
              </template>
            </StatePanel>

            <template v-else>
              <article v-if="featuredItem" class="featured-plugin">
                <div class="featured-mark" aria-hidden="true">{{ featuredInitials }}</div>
                <div class="featured-copy">
                  <span class="featured-badge">精选扩展</span>
                  <h2>{{ featuredItem.package }}</h2>
                  <p>{{ featuredItem.summary || '为 AUTO-MAS 提供更多自动化能力。' }}</p>
                  <div class="featured-meta">
                    <span>v{{ featuredItem.version || '未知' }}</span>
                    <span aria-hidden="true">·</span>
                    <span>{{ isInstalled(featuredItem.package) ? '已安装' : '可获取' }}</span>
                  </div>
                </div>
                <div class="featured-action" @click.stop>
                  <a-button
                    v-if="!isInstalled(featuredItem.package)"
                    type="primary"
                    size="large"
                    :loading="isOperationLoading(featuredItem.package)"
                    :disabled="!isConnected"
                    @click="requestInstall(featuredItem.package, 'install')"
                  >
                    获取
                  </a-button>
                  <a-button
                    v-else
                    size="large"
                    :loading="isOperationLoading(featuredItem.package)"
                    :disabled="!isConnected || isUpToDate(featuredItem)"
                    @click="requestInstall(featuredItem.package, 'update')"
                  >
                    {{ isUpToDate(featuredItem) ? '已是最新' : '更新' }}
                  </a-button>
                </div>
              </article>

              <div class="results-heading">
                <h2>热门推荐</h2>
                <a-button v-if="hasActiveFilters" type="link" @click="clearFilters">
                  清除筛选
                </a-button>
              </div>

              <div class="card-grid">
                <a-card
                  v-for="item in filteredItems"
                  :key="item.package"
                  class="plugin-card"
                  :class="{ 'plugin-card--link': Boolean(item.project_url) }"
                  :bordered="false"
                  @click="goToPackage(item.project_url)"
                >
                  <template #title>
                    <div class="card-title">
                      <span class="plugin-avatar" aria-hidden="true">{{
                        packageInitials(item.package)
                      }}</span>
                      <div class="package-heading">
                        <span class="name">{{ item.package }}</span>
                        <span class="package-version">v{{ item.version || '未知' }}</span>
                      </div>
                      <span v-if="isInstalled(item.package)" class="installed-pill">✓ 已安装</span>
                    </div>
                  </template>

                  <div class="summary">{{ item.summary || '暂无简介' }}</div>

                  <div class="version-grid" aria-label="插件版本信息">
                    <div>
                      <span>最新版本</span>
                      <strong>{{ item.version || '未知' }}</strong>
                    </div>
                    <div>
                      <span>本机版本</span>
                      <strong v-if="isInstalled(item.package)">
                        {{ installedVersion(item.package) || '版本未上报' }}
                      </strong>
                      <strong v-else>未安装</strong>
                    </div>
                  </div>

                  <div class="card-actions">
                    <a-space @click.stop>
                      <a-button
                        v-if="!isInstalled(item.package)"
                        type="primary"
                        :loading="isOperationLoading(item.package)"
                        :disabled="!isConnected"
                        @click="requestInstall(item.package, 'install')"
                      >
                        安装
                      </a-button>
                      <template v-else>
                        <a-button
                          type="primary"
                          :loading="isOperationLoading(item.package)"
                          :disabled="!isConnected || isUpToDate(item)"
                          @click="requestInstall(item.package, 'update')"
                        >
                          {{ isUpToDate(item) ? '已是最新' : '更新到最新版' }}
                        </a-button>
                        <a-popconfirm
                          title="确定卸载这个插件包吗？"
                          ok-text="卸载"
                          cancel-text="取消"
                          :disabled="!isConnected || isOperationLoading(item.package)"
                          @confirm="requestUninstall(item.package)"
                        >
                          <a-button
                            danger
                            :loading="isOperationLoading(item.package)"
                            :disabled="!isConnected"
                          >
                            卸载
                          </a-button>
                        </a-popconfirm>
                      </template>
                    </a-space>
                    <div v-if="isOperationLoading(item.package)" class="operation-progress">
                      <span>{{ operationLabel(item.package) }}</span>
                      <a-progress
                        :percent="operationProgressValue(item.package)"
                        size="small"
                        :show-info="true"
                      />
                    </div>
                  </div>
                </a-card>
              </div>
            </template>
          </div>
        </section>
      </main>

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
        <StatePanel
          type="info"
          title="输入精确包名后，将直接从 PyPI 下载并安装到当前插件目录。"
          compact
        />
        <template #footer>
          <a-space>
            <a-button :disabled="manualInstallSubmitting" @click="closeManualInstall"
              >取消</a-button
            >
            <a-button
              type="primary"
              :loading="manualInstallSubmitting"
              @click="submitManualInstall"
            >
              开始安装
            </a-button>
          </a-space>
        </template>
      </a-modal>
    </PluginErrorBoundary>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useWebSocket } from '@/composables/useWebSocket'
import LoadingSkeleton from '@/components/v6/LoadingSkeleton.vue'
import StatePanel from '@/components/mac/StatePanel.vue'
import MacPageHeader from '@/components/mac/PageHeader.vue'
import PluginErrorBoundary from '@/plugins/ui/PluginErrorBoundary.vue'
import {
  buildInstalledState,
  filterMarketItems,
  isSameVersion,
  mergeInstalledVersions,
  normalizePackageName,
  type InstalledPackageState,
  type InstalledVersionMap,
  type InstallFilter,
  type MarketItem,
  type MarketSnapshot,
} from '@/views/plugin-market/marketModel'
import { loadMarketSnapshotCache, saveMarketSnapshotCache } from '@/views/plugin-market/marketCache'
import { fetchInstalledVersionMap } from '@/views/plugin-market/installedVersions'
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

interface PluginMarketMessageData {
  requestId?: string
  status?: string
  message?: string
  payload?: Record<string, unknown>
}

const logger = window.electronAPI.getLogger('插件市场')

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
const connectionHint = computed(() => {
  switch (state.value) {
    case 'open':
      return '市场通道可用'
    case 'connecting':
    case 'reconnecting':
      return '正在协商后端连接'
    case 'closed':
      return '市场操作已暂时禁用'
    default:
      return '等待后端连接'
  }
})

const marketSnapshot = ref<MarketSnapshot | null>(null)
const marketLoadError = ref('')
const installedState = ref<Record<string, InstalledPackageState>>({})
// 本机已安装 distribution 的真实版本（来自插件网关 plugin_packages）。
// 市场快照 installed_map 目前只有布尔位，本机版本显示靠它补齐。
const installedVersionMap = ref<InstalledVersionMap>({})
const operationLoading = ref<Record<string, boolean>>({})
const operationProgress = ref<Record<string, number>>({})
const operationStage = ref<Record<string, string>>({})
const operationKind = ref<Record<string, PluginOperationKind>>({})
type MarketTab = 'recommended' | 'all' | 'installed'
const marketTab = ref<MarketTab>('recommended')
const searchKeyword = ref('')
const installFilter = ref<InstallFilter>('all')
const prefixFilter = ref('')
const snapshotLoading = ref(false)
const manualInstallVisible = ref(false)
const manualPackageName = ref('')
const pendingManualPackage = ref('')

const lastInfoType = ref<'success' | 'error' | 'info' | 'warning'>('info')
const lastInfoMessage = ref('')

const subscriptionIds: string[] = []
type PluginOperationKind = 'install' | 'update' | 'uninstall'

const installFilterOptions = [
  { label: '全部状态', value: 'all' },
  { label: '已安装', value: 'installed' },
  { label: '未安装', value: 'available' },
]

const prefixFilterOptions = computed(() => [
  { label: '全部前缀', value: '' },
  ...(marketSnapshot.value?.prefix_tags || []).map(prefix => ({
    label: prefix,
    value: prefix,
  })),
])

const packageInitials = (packageName: string) => {
  const segments = packageName
    .replace(/^auto[-_]?mas[-_]?/i, '')
    .split(/[-_]/)
    .filter(Boolean)
  return (
    segments
      .slice(0, 2)
      .map(segment => segment[0])
      .join('') || 'AM'
  ).toUpperCase()
}

const featuredItem = computed(() => {
  const items = marketSnapshot.value?.items ?? []
  return (
    items.find(item => /(?:^|[-_])m9a(?:$|[-_])/i.test(item.package)) ??
    items.find(item => /maafw|hsr/i.test(item.package)) ??
    items[0] ??
    null
  )
})

const featuredInitials = computed(() =>
  featuredItem.value ? packageInitials(featuredItem.value.package) : 'AM'
)

const setInfo = (msg: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') => {
  lastInfoType.value = type
  lastInfoMessage.value = msg
}

const applySnapshot = (snapshot: MarketSnapshot) => {
  marketSnapshot.value = snapshot
  installedState.value = buildInstalledState(snapshot.installed_map)
}

const saveSnapshotCache = (snapshot: MarketSnapshot) => {
  if (!saveMarketSnapshotCache(snapshot)) {
    logger.warn('写入插件市场缓存失败')
  }
}

// 后台补齐本机版本；失败静默（界面回退到"版本未上报"）。
const refreshInstalledVersions = async () => {
  try {
    installedVersionMap.value = await fetchInstalledVersionMap()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`获取本机插件版本失败: ${errorMsg}`)
  }
}

const updateInstalledState = (pkg: string, installed: boolean) => {
  const normalized = normalizePackageName(pkg)
  const previousVersion = installedState.value[normalized]?.version || ''
  installedState.value = {
    ...installedState.value,
    [normalized]: { installed, version: installed ? previousVersion : '' },
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

// 页面可能在主连接协商期间挂载；连接恢复后只补发一次首次快照请求。
let pendingInitialSnapshot = false

const requestSnapshot = async (options?: { quiet?: boolean }) => {
  if (snapshotLoading.value) {
    return
  }
  if (!isConnected.value) {
    pendingInitialSnapshot = true
    marketLoadError.value = '插件市场连接尚未就绪'
    setInfo('等待与后端建立连接后获取市场数据...', 'info')
    return
  }
  snapshotLoading.value = true
  marketLoadError.value = ''
  try {
    const response = await request(
      WS_ID_PLUGIN_MARKET,
      WS_MARKET_SNAPSHOT_REQUEST,
      [WS_MARKET_SNAPSHOT_RESPONSE, WS_MARKET_ERROR],
      { perPrefixLimit: 60 },
      15000
    )
    if (response.type === WS_MARKET_ERROR) {
      const errorData = response.data as PluginMarketMessageData
      marketLoadError.value = errorData.message || '插件市场返回错误'
      setInfo(marketLoadError.value, 'error')
      return
    }
    const data = response.data as PluginMarketMessageData
    applySnapshot((data.payload || {}) as unknown as MarketSnapshot)
    if (marketSnapshot.value) {
      saveSnapshotCache(marketSnapshot.value)
    }
    void refreshInstalledVersions()
    if (!options?.quiet) {
      setInfo('市场快照已更新', 'success')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`获取市场快照失败: ${errorMsg}`)
    marketLoadError.value = errorMsg
    setInfo(`获取市场快照失败: ${errorMsg}`, 'error')
  } finally {
    snapshotLoading.value = false
  }
}

// 展示用安装状态：快照 installed_map 的布尔位 + 插件网关补齐的本机版本
const displayedInstalledState = computed(() =>
  mergeInstalledVersions(installedState.value, installedVersionMap.value)
)

const isInstalled = (pkg: string) =>
  Boolean(displayedInstalledState.value[normalizePackageName(pkg)]?.installed)

const installedVersion = (pkg: string) =>
  displayedInstalledState.value[normalizePackageName(pkg)]?.version || ''

const isUpToDate = (item: MarketItem) =>
  isInstalled(item.package) && isSameVersion(installedVersion(item.package), item.version)

const isOperationLoading = (pkg: string) =>
  Boolean(operationLoading.value[normalizePackageName(pkg)])

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
    [normalizePackageName(pkg)]: loading,
  }
}

const setOperationState = (
  pkg: string,
  kind: PluginOperationKind,
  progress: number,
  stage: string
) => {
  const normalized = normalizePackageName(pkg)
  operationKind.value = { ...operationKind.value, [normalized]: kind }
  operationProgress.value = { ...operationProgress.value, [normalized]: progress }
  operationStage.value = { ...operationStage.value, [normalized]: stage }
}

const operationProgressValue = (pkg: string) =>
  operationProgress.value[normalizePackageName(pkg)] ?? 0

const operationLabel = (pkg: string) => {
  const normalized = normalizePackageName(pkg)
  const kind = operationKind.value[normalized]
  const stage = operationStage.value[normalized]
  const kindLabel = kind === 'update' ? '更新' : kind === 'uninstall' ? '卸载' : '安装'
  const stageLabels: Record<string, string> = {
    queued: '等待处理',
    installing: '正在写入',
    completed: '正在刷新',
    uninstalling: '正在卸载',
  }
  return `${kindLabel} · ${stageLabels[stage] || '处理中'}`
}

const requestInstall = (pkg: string, kind: 'install' | 'update' = 'install'): boolean => {
  const packageName = String(pkg || '').trim()
  if (!packageName) {
    message.warning('请先输入包名')
    return false
  }
  if (isOperationLoading(packageName)) {
    return false
  }
  markOperation(packageName, true)
  setOperationState(packageName, kind, 5, 'queued')
  if (!sendPluginRequest(WS_PLUGIN_INSTALL_REQUEST, { package: packageName })) {
    markOperation(packageName, false)
    return false
  }
  return true
}

const requestUninstall = (pkg: string) => {
  if (isOperationLoading(pkg)) {
    return
  }
  markOperation(pkg, true)
  setOperationState(pkg, 'uninstall', 10, 'uninstalling')
  if (!sendPluginRequest(WS_PLUGIN_UNINSTALL_REQUEST, { package: pkg })) {
    markOperation(pkg, false)
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
  pendingManualPackage.value = normalizePackageName(packageName)
  if (!requestInstall(packageName, 'install')) {
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

const onPluginMessage = (event: string, envelope: PluginMarketMessageData) => {
  const status = String(envelope.status || 'success')
  const payload = envelope.payload || {}

  if (event === WS_PLUGIN_INSTALL_PROGRESS) {
    const pkg = String(payload.package || '')
    const progress = Number(payload.progress || 0)
    if (pkg) {
      const normalized = normalizePackageName(pkg)
      setOperationState(
        pkg,
        operationKind.value[normalized] || 'install',
        Math.max(0, Math.min(progress, 100)),
        String(payload.stage || 'installing')
      )
      setInfo(`${operationLabel(pkg)}: ${pkg} (${progress}%)`, 'info')
    }
    return
  }

  if (event === WS_PLUGIN_INSTALL_RESULT) {
    const pkg = String(payload.package || '')
    const normalized = normalizePackageName(pkg)
    const kind = operationKind.value[normalized] || 'install'
    if (pkg) {
      markOperation(pkg, false)
    }
    const ok = status !== 'error' && Boolean(payload.success)
    if (ok && pkg) {
      updateInstalledState(pkg, true)
    }
    if (pkg && normalizePackageName(pkg) === pendingManualPackage.value) {
      if (ok) {
        manualPackageName.value = ''
        manualInstallVisible.value = false
      }
      pendingManualPackage.value = ''
    }
    const actionLabel = kind === 'update' ? '更新' : '安装'
    const resultMessage = ok ? `${actionLabel}成功: ${pkg}` : `${actionLabel}失败: ${pkg}`
    setInfo(envelope.message || resultMessage, ok ? 'success' : 'error')
    if (ok) {
      message.success(resultMessage)
      void requestSnapshot({ quiet: true })
    } else {
      message.error(envelope.message || resultMessage)
    }
    return
  }

  if (event === WS_PLUGIN_UNINSTALL_RESULT) {
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
      void requestSnapshot({ quiet: true })
    } else {
      message.error(envelope.message || '卸载失败')
    }
    return
  }

  if (event === WS_PLUGIN_INSTALLED_SYNC) {
    const pkg = String(payload.package || '')
    if (!pkg) {
      return
    }
    updateInstalledState(pkg, Boolean(payload.installed))
    markOperation(pkg, false)
    return
  }

  if (event === WS_MARKET_ERROR) {
    snapshotLoading.value = false
    const msg = envelope.message || '插件通道发生错误'
    marketLoadError.value = msg
    setInfo(msg, 'error')
    message.error(msg)
    return
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
  return filterMarketItems(
    snapshot.items,
    displayedInstalledState.value,
    searchKeyword.value,
    installFilter.value,
    prefixFilter.value
  )
})

const hasActiveFilters = computed(
  () =>
    Boolean(searchKeyword.value.trim()) ||
    installFilter.value !== 'all' ||
    Boolean(prefixFilter.value)
)

const clearFilters = () => {
  searchKeyword.value = ''
  installFilter.value = 'all'
  prefixFilter.value = ''
  marketTab.value = 'all'
}

const selectMarketTab = (tab: MarketTab) => {
  searchKeyword.value = ''
  prefixFilter.value = ''
  installFilter.value = tab === 'installed' ? 'installed' : 'all'
  marketTab.value = tab
}

const syncMarketTabFromInstallFilter = (value: InstallFilter) => {
  marketTab.value = value === 'installed' ? 'installed' : 'all'
}

onMounted(() => {
  subscriptionIds.push(
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_INSTALL_PROGRESS }, msg =>
      onPluginMessage(msg.type, msg.data as PluginMarketMessageData)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_INSTALL_RESULT }, msg =>
      onPluginMessage(msg.type, msg.data as PluginMarketMessageData)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_UNINSTALL_RESULT }, msg =>
      onPluginMessage(msg.type, msg.data as PluginMarketMessageData)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_PLUGIN_INSTALLED_SYNC }, msg =>
      onPluginMessage(msg.type, msg.data as PluginMarketMessageData)
    ),
    subscribe({ id: WS_ID_PLUGIN_MARKET, type: WS_MARKET_ERROR }, msg =>
      onPluginMessage(msg.type, msg.data as PluginMarketMessageData)
    )
  )

  const cachedSnapshot = loadMarketSnapshotCache()
  if (cachedSnapshot) {
    // 缓存可能来自本页上次访问，也可能来自 appEntry 的启动预热
    applySnapshot(cachedSnapshot)
    setInfo('已加载本地缓存，点击“刷新”可获取最新市场数据', 'info')
    void refreshInstalledVersions()
  } else {
    void requestSnapshot()
  }
})

watch(
  () => state.value,
  status => {
    if (status === 'open' && pendingInitialSnapshot) {
      pendingInitialSnapshot = false
      void requestSnapshot()
    }
  }
)

onUnmounted(() => {
  subscriptionIds.forEach(id => unsubscribe(id))
  subscriptionIds.length = 0
})
</script>

<style scoped>
.plugin-market-page {
  height: 100%;
  min-height: 0;
  min-width: 0;
  container: plugin-market / inline-size;
  padding: var(--v6-space-3) var(--v6-content-padding-inline) 0;
  background: var(--v6-color-window);
  color: var(--v6-color-text);
}

.plugin-market-page :deep(.plugin-error-boundary) {
  height: 100%;
}

.market-shell {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: transparent;
}

.market-header {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: minmax(190px, 1fr) auto minmax(190px, 1fr);
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-4);
  min-height: 64px;
  padding: 0 0 var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.connection-pill {
  justify-self: end;
}

/* 页头位于市场三列网格首格：抵消 PageHeader 的全宽内边距保持网格对齐 */
.market-heading :deep(.mac-page-header) {
  padding: 0;
}

.market-tabs {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: 8px;
  background: var(--v6-color-fill-tertiary);
}

.market-tabs button {
  min-width: 64px;
  height: 32px;
  padding: 0 14px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--v6-color-text-secondary);
  cursor: pointer;
}

.market-tabs button:hover {
  color: var(--v6-color-text);
}

.market-tabs button.is-active {
  background: var(--v6-color-primary);
  color: #fff;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--v6-color-primary) 28%, transparent);
}

.connection-pill {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  min-width: 154px;
  padding: var(--v6-space-2) var(--v6-space-3);
  border-radius: var(--v6-radius-full);
  background: var(--v6-vibrancy-hover);
  color: var(--v6-color-text-secondary);
}

.connection-pill > span:last-child {
  display: grid;
}

.connection-pill strong {
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-sm);
  line-height: 1.2;
}

.connection-pill small {
  font-size: var(--v6-font-size-xs);
}

.connection-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--v6-radius-full);
  background: var(--v6-color-warning);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--v6-color-warning) 15%, transparent);
}

.connection-pill--online .connection-dot {
  background: var(--v6-color-success);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--v6-color-success) 15%, transparent);
}

.market-toolbar {
  flex-shrink: 0;
  display: grid;
  grid-template-columns: minmax(220px, 1fr) 132px minmax(140px, 180px) auto;
  gap: var(--v6-space-2);
  align-items: center;
  padding: var(--v6-space-3) 0;
}

.market-search {
  justify-self: end;
  max-width: 320px;
}

.market-search,
.market-filter {
  width: 100%;
}

.toolbar-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--v6-space-2);
}

.market-feedback {
  flex-shrink: 0;
  margin: 0 0 var(--v6-space-2);
  padding: var(--v6-space-2) var(--v6-space-3);
  border-radius: var(--v6-radius-md);
  background: var(--v6-vibrancy-hover);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
}

.market-feedback--success {
  color: var(--v6-color-success);
}

.market-feedback--error {
  color: var(--v6-color-error);
}

.market-feedback--warning {
  color: var(--v6-color-warning);
}

.snapshot-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-2);
  padding: var(--v6-space-2) 0;
  border-block: 1px solid var(--v6-color-border-subtle);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
}

.snapshot-bar strong {
  color: var(--v6-color-text);
}

.snapshot-source {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
}

.offline-label,
.source-badge {
  padding: var(--v6-space-0-5) var(--v6-space-2);
  border-radius: var(--v6-radius-full);
  background: var(--v6-vibrancy-selected);
  color: var(--v6-color-info);
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-semibold);
}

.market-content {
  flex: 1;
  min-height: 0;
}

.market-scroll {
  height: 100%;
  overflow: auto;
  padding: var(--v6-space-3) 0 var(--v6-space-6);
}

.featured-plugin {
  display: grid;
  grid-template-columns: 124px minmax(0, 1fr) auto;
  align-items: center;
  gap: 28px;
  min-height: 200px;
  margin-bottom: 28px;
  padding: 28px 32px;
  overflow: hidden;
  border-radius: 20px;
  background:
    radial-gradient(circle at 76% 18%, rgb(255 255 255 / 18%), transparent 34%),
    linear-gradient(125deg, #ff7a52 0%, #ff5f74 45%, #b85de0 100%);
  color: #fff;
  box-shadow: 0 18px 44px rgb(138 62 128 / 20%);
}

.featured-mark {
  display: grid;
  width: 116px;
  height: 116px;
  place-items: center;
  border-radius: 28px;
  background: rgb(255 255 255 / 88%);
  color: #ff5f45;
  box-shadow: 0 12px 26px rgb(65 24 50 / 18%);
  font-size: 30px;
  font-weight: 750;
  letter-spacing: -0.05em;
}

.featured-copy {
  min-width: 0;
}

.featured-copy h2 {
  margin: 14px 0 8px;
  overflow: hidden;
  color: #fff;
  font-size: clamp(26px, 3vw, 38px);
  font-weight: 740;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.featured-copy p {
  max-width: 720px;
  margin: 0;
  color: rgb(255 255 255 / 88%);
  line-height: 1.6;
}

.featured-badge {
  display: inline-flex;
  padding: 5px 11px;
  border-radius: 999px;
  background: rgb(255 255 255 / 22%);
  font-size: 12px;
  font-weight: 650;
}

.featured-meta {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  color: rgb(255 255 255 / 78%);
  font-size: 12px;
}

.featured-action :deep(.ant-btn) {
  min-width: 92px;
  border: 0;
  border-radius: 999px;
  background: rgb(255 255 255 / 92%);
  color: #e54f5f;
  font-weight: 650;
}

.results-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 0 16px;
}

.results-heading h2 {
  margin: 0;
  font-size: 22px;
  letter-spacing: -0.02em;
}

.state-description {
  margin: 0;
  color: var(--v6-color-text-secondary);
  line-height: var(--v6-line-height-normal);
}

/* iPad 设置式自适应双栏：CSS multi-column 让卡片在两列内各自按内容高度堆叠，
   矮卡不再被行等高拉伸（column 流向左列先满，属预期）。 */
.card-grid {
  columns: 2;
  column-gap: var(--v6-space-3);
  padding-bottom: var(--v6-space-2);
}

.plugin-card {
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: color-mix(in srgb, var(--v6-color-surface) 84%, transparent);
  box-shadow: none;
  /* 多列布局下卡片为独立块：inline-block + width:100% + break-inside 防跨列断裂 */
  display: inline-block;
  width: 100%;
  vertical-align: top;
  break-inside: avoid;
  margin-bottom: var(--v6-space-3);
  transition:
    border-color var(--v6-motion-fast) var(--v6-ease-out),
    box-shadow var(--v6-motion-fast) var(--v6-ease-out),
    transform var(--v6-motion-fast) var(--v6-ease-out);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.plugin-avatar {
  display: grid;
  width: 48px;
  height: 48px;
  flex: 0 0 48px;
  place-items: center;
  border-radius: 13px;
  background: linear-gradient(145deg, #7359e9, #5b47d6);
  color: #fff;
  box-shadow: 0 8px 18px rgb(91 71 214 / 22%);
  font-size: 15px;
  font-weight: 760;
}

.plugin-card--link {
  cursor: pointer;
}

.plugin-card--link:hover {
  border-color: var(--v6-color-info-border);
  box-shadow: var(--v6-shadow-card);
  transform: translateY(-1px);
}

.plugin-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-3);
  padding: var(--v6-space-3);
}

.package-heading {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.package-version {
  color: var(--v6-color-text-tertiary);
  font-size: 11px;
  font-weight: 450;
}

.installed-pill {
  margin-left: auto;
  padding: 4px 9px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--v6-color-success) 12%, transparent);
  color: var(--v6-color-success);
  font-size: 11px;
  white-space: nowrap;
}

.card-title .name {
  min-width: 0;
  color: var(--v6-color-text);
  font-weight: var(--v6-font-weight-semibold);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary {
  color: var(--v6-color-text-secondary);
  min-height: 44px;
  line-height: var(--v6-line-height-normal);
}

.version-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v6-space-2);
}

.version-grid > div {
  display: grid;
  gap: var(--v6-space-0-5);
  padding: var(--v6-space-2);
  border-radius: var(--v6-radius-md);
  background: var(--v6-vibrancy-hover);
}

.version-grid span {
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-xs);
}

.version-grid strong {
  min-width: 0;
  overflow: hidden;
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-sm);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-actions {
  margin-top: auto;
  padding-top: var(--v6-space-1);
}

.card-actions :deep(.ant-space) {
  flex-wrap: wrap;
}

.card-actions :deep(.ant-btn) {
  min-width: 88px;
}

.operation-progress {
  margin-top: var(--v6-space-2);
}

:root[data-perf-mode='low'] .market-shell,
:root[data-perf-mode='low'] .plugin-card,
:root[data-perf-mode='low'] .plugin-card--link:hover {
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  box-shadow: none;
  transform: none;
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .plugin-card {
    transition: none;
  }

  .plugin-card--link:hover {
    transform: none;
  }
}

@container plugin-market (max-width: 960px) {
  .card-grid {
    columns: 1;
  }

  .market-toolbar {
    grid-template-columns: minmax(220px, 1fr) 132px auto;
  }

  .market-filter--prefix {
    display: none;
  }
}

/* .plugin-market-page 自身规则须由外层 app-shell 的 app-content 容器驱动
   (@container 不能命中声明容器的元素自身) */
@container app-content (max-width: 760px) {
  .plugin-market-page {
    padding: var(--v6-space-3);
  }
}

@container plugin-market (max-width: 760px) {
  .market-header {
    grid-template-columns: minmax(0, 1fr);
    align-items: stretch;
    padding: var(--v6-space-4);
  }

  .connection-pill {
    justify-self: start;
    min-width: 0;
  }

  .market-toolbar {
    grid-template-columns: 1fr 120px;
    padding: 0 var(--v6-space-4) var(--v6-space-3);
  }

  .toolbar-actions {
    grid-column: 1 / -1;
  }

  .market-feedback {
    margin-inline: var(--v6-space-4);
  }

  .snapshot-bar {
    align-items: flex-start;
    padding-inline: var(--v6-space-4);
  }

  .snapshot-source {
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .market-scroll {
    padding-inline: var(--v6-space-4);
  }
}

@container plugin-market (max-width: 540px) {
  .market-tabs {
    width: 100%;
    overflow-x: auto;
  }

  .market-tabs button {
    flex: 1 0 auto;
  }

  .snapshot-bar {
    flex-direction: column;
  }

  .market-toolbar {
    grid-template-columns: 1fr;
  }

  .toolbar-actions {
    grid-column: auto;
    justify-content: stretch;
  }

  .toolbar-actions :deep(.ant-btn) {
    flex: 1;
  }

  .snapshot-source {
    justify-content: flex-start;
  }
}
</style>
