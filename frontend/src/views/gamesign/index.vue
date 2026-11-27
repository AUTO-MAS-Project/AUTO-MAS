<!--
  游戏社区页容器。
  导航用 pill 切换四个视图（签到 / 日常便笺 / 抽卡记录 / 帐号管理），
  视图只做展示，配置读写、签到触发、帐号加载都收敛在这里，
  这样切换视图不会各写一套提交与回滚。
-->
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CheckSquareOutlined, UsergroupAddOutlined } from '@ant-design/icons-vue'
import type { ToolsConfig_SignFlow } from '@/api'
import { useToolsApi, type ToolsViewConfig } from '@/composables/useToolsApi'
import { useToolsStatusPolling } from '@/composables/useToolsStatusPolling'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_ID_SIGN_FLOW,
  WS_SIGN_FLOW_RESULT_UPDATED,
  type WSSignFlowResultData,
} from '@/services/websocket/types'
import { AppPage, PageHeader, PageSurface, StateView } from '@/components/ui'
import AccountsPage from './AccountsPage.vue'
import CommunityActivityView from './CommunityActivityView.vue'
import GachaPage from './GachaPage.vue'
import SignHomePage from './SignHomePage.vue'
import { useGameSignAccounts } from './useGameSignAccounts'
import { useManualSign } from './useManualSign'

const { t } = useI18n()

defineOptions({ name: 'SignFlowPage' })

const logger = window.electronAPI.getLogger('游戏社区')
const route = useRoute()
const router = useRouter()

type CommunityView = 'sign' | 'activity' | 'gacha' | 'accounts'

const VIEW_KEYS: readonly CommunityView[] = ['sign', 'activity', 'gacha', 'accounts']

/** 导航文案显式列出：动态拼接的 key 无法被 i18n 审计识别 */
const VIEW_LABELS: Record<CommunityView, string> = {
  sign: 'core.signflow.nav.sign',
  activity: 'core.signflow.nav.activity',
  gacha: 'core.signflow.nav.gacha',
  accounts: 'core.signflow.nav.accounts',
}

const { loading, getTools, updateTools } = useToolsApi()
const { subscribe, unsubscribe } = useWebSocket()

// 工具数据（保留完整 ToolsConfig，避免更新时覆盖其它工具的配置）
const toolsConfig = reactive<ToolsViewConfig>({
  SignFlow: {
    Enabled: false,
    NotifyEnabled: false,
    ActivityEnabled: true,
    RunOnStartup: false,
    LastSignDate: '2000-01-01T00:00:00+08:00',
    Status: '-',
    Result: '{}',
  },
})

// 本地编辑状态
const editingConfig = reactive<ToolsViewConfig>({
  SignFlow: {
    Enabled: false,
    NotifyEnabled: false,
    ActivityEnabled: true,
    RunOnStartup: false,
    LastSignDate: '2000-01-01T00:00:00+08:00',
    Status: '-',
    Result: '{}',
  },
})

const toolsLoaded = ref(false)
/** 配置加载失败原因：失败时页面只剩空壳开关，必须给重试入口而不是静默留白 */
const loadError = ref<string | null>(null)

let signFlowSubscriptionId: string | null = null

// 卸载守卫：组件卸载后阻止异步回调写入响应式状态
let isMounted = true

const activityEnabled = computed(
  () => toolsLoaded.value && editingConfig.SignFlow?.ActivityEnabled !== false
)

const activeView = computed<CommunityView>(() => {
  const tab = route.query.tab
  if (typeof tab === 'string' && VIEW_KEYS.includes(tab as CommunityView)) {
    if (tab === 'activity' && !activityEnabled.value) return 'sign'
    return tab as CommunityView
  }
  return 'sign'
})

const handleViewChange = (key: string | number) => {
  const view: CommunityView = VIEW_KEYS.includes(key as CommunityView)
    ? (key as CommunityView)
    : 'sign'
  if (view === 'activity' && !activityEnabled.value) return
  void router.replace({
    path: '/signflow',
    query: view === 'sign' ? {} : { tab: view },
  })
}

const {
  accounts,
  signResult,
  load: loadAccounts,
} = useGameSignAccounts(() => editingConfig.SignFlow?.Result)

const refreshSignFlowConfig = () => updateStatus()

const { signLoading, run: runManualSign } = useManualSign(async () => {
  await refreshSignFlowConfig()
  await loadAccounts()
})

const syncSignFlowResult = (result: unknown) => {
  if (!isMounted || typeof result !== 'string') return
  if (toolsConfig.SignFlow) {
    toolsConfig.SignFlow.Result = result
  }
  if (editingConfig.SignFlow) {
    editingConfig.SignFlow.Result = result
  }
}

// 状态轮询：签到视图激活时才拉；签到已启用 5 s 一次，否则 30 s
const { updateStatus, startStatusPolling, stopStatusPolling } = useToolsStatusPolling({
  applyStatus: data => {
    if (data.SignFlow?.Status) {
      toolsConfig.SignFlow!.Status = data.SignFlow.Status
    }
    // 「上次签到」是只读展示字段，必须跟随轮询刷新：手动签到或凭据变更后
    // 后端会重写甚至重置该日期，只在挂载时读一次会一直显示旧值。
    if (data.SignFlow?.LastSignDate) {
      toolsConfig.SignFlow!.LastSignDate = data.SignFlow.LastSignDate
      if (editingConfig.SignFlow) {
        editingConfig.SignFlow.LastSignDate = data.SignFlow.LastSignDate
      }
    }
    syncSignFlowResult(data.SignFlow?.Result)
  },
  isActive: () => toolsConfig.SignFlow?.Enabled === true,
  enabled: () => activeView.value === 'sign',
  invalidMessage: () => t('core.signflow.statusInvalid'),
  logger,
})

// 加载配置
const loadTools = async () => {
  loadError.value = null
  try {
    const data = await getTools()
    if (!data.SignFlow) {
      data.SignFlow = {
        Enabled: false,
        NotifyEnabled: false,
        ActivityEnabled: true,
        RunOnStartup: false,
        LastSignDate: '2000-01-01T00:00:00+08:00',
        Status: '-',
        Result: '{}',
      }
    }
    data.SignFlow.ActivityEnabled ??= true
    Object.assign(toolsConfig, data)
    Object.assign(editingConfig, JSON.parse(JSON.stringify(data)))
    toolsLoaded.value = true
    logger.info('游戏社区配置加载完成')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载游戏社区配置失败: ${errorMsg}`)
    loadError.value = errorMsg
  }
}

/** 重试加载：配置与帐号是两路请求，一起重来避免只恢复一半 */
const handleRetryLoad = async () => {
  await loadTools()
  if (!loadError.value) await loadAccounts()
}

// 只提交当前 SignFlow 字段，避免并发覆盖签到状态或其它工具配置。
type SignFlowFieldKey = keyof ToolsConfig_SignFlow

const handleSignFlowFieldChange = async <K extends SignFlowFieldKey>(
  key: K,
  value: ToolsConfig_SignFlow[K]
) => {
  const editingSignFlow = editingConfig.SignFlow
  if (!editingSignFlow) return

  const previousValue = editingSignFlow[key]

  try {
    editingSignFlow[key] = value
    // 开关是即时保存，成功提示会随每次点击弹一条；这里只保留失败提示，
    // 避免连点几个开关就把页面刷满 toast。
    await updateTools(
      { SignFlow: { [key]: value } as Partial<ToolsConfig_SignFlow> },
      { silent: true }
    )

    if (toolsConfig.SignFlow && key !== 'Status' && key !== 'Result') {
      toolsConfig.SignFlow[key] = value
    }

    logger.info(`SignFlow.${key} 已保存`)
  } catch (error) {
    // 仅在当前值仍是本次提交值时回滚，避免较早请求失败覆盖更新后的操作。
    if (editingSignFlow[key] === value) {
      editingSignFlow[key] = previousValue
    }
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 SignFlow.${key} 失败: ${errorMsg}`)
    throw error
  }
}

const goAccounts = () => handleViewChange('accounts')

watch(activeView, view => {
  if (view !== 'sign' || !isMounted) return
  // 签到页展示的「凭据已绑定」和结果里的账号名都来自帐号列表，
  // 切回来时除了刷新签到状态，还要重拉一次帐号，避免帐号管理页改完后仍显示旧快照。
  void updateStatus()
  void loadAccounts()
})

watch(activityEnabled, enabled => {
  if (!enabled && route.query.tab === 'activity' && isMounted) {
    void router.replace({ path: '/signflow', query: {} })
  }
})

onMounted(async () => {
  signFlowSubscriptionId = subscribe(
    { id: WS_ID_SIGN_FLOW, type: WS_SIGN_FLOW_RESULT_UPDATED },
    wsMessage => {
      const data = wsMessage.data as unknown as WSSignFlowResultData
      syncSignFlowResult(data.result)
    }
  )
  await loadTools()
  await loadAccounts()
  startStatusPolling()
})

onUnmounted(() => {
  isMounted = false
  stopStatusPolling()
  if (signFlowSubscriptionId) {
    unsubscribe(signFlowSubscriptionId)
    signFlowSubscriptionId = null
  }
})
</script>

<template>
  <AppPage layout="scroll">
    <PageHeader :title="t('core.signflow.title')" :subtitle="t('core.signflow.subtitle')">
      <template #actions>
        <a-button :disabled="loading" @click="goAccounts">
          <template #icon><UsergroupAddOutlined /></template>
          {{ t('core.signflow.nav.accounts') }}
        </a-button>
        <a-button
          type="primary"
          :loading="signLoading"
          :disabled="loading || !editingConfig.SignFlow?.Enabled"
          @click="runManualSign"
        >
          <template #icon><CheckSquareOutlined /></template>
          {{ t('core.signflow.section.signAll') }}
        </a-button>
      </template>
    </PageHeader>

    <PageSurface padding="none" :scrollable="false">
      <nav class="view-nav" role="tablist">
        <button
          v-for="view in VIEW_KEYS"
          :key="view"
          type="button"
          role="tab"
          :aria-selected="activeView === view"
          :class="['view-tab', activeView === view ? 'is-active' : '']"
          :disabled="view === 'activity' && !activityEnabled"
          @click="handleViewChange(view)"
        >
          {{ t(VIEW_LABELS[view]) }}
        </button>
      </nav>

      <div class="view-body">
        <StateView
          v-if="loadError"
          :error="loadError"
          empty
          :min-height="240"
          @retry="handleRetryLoad"
        />
        <SignHomePage
          v-else-if="activeView === 'sign' && editingConfig.SignFlow"
          :config="editingConfig.SignFlow"
          :result="signResult"
          :accounts="accounts"
          :disabled="loading"
          :sign-loading="signLoading"
          :on-field-change="handleSignFlowFieldChange"
          @manage="goAccounts"
          @sign="runManualSign"
          @refresh="refreshSignFlowConfig"
        />
        <CommunityActivityView v-else-if="activeView === 'activity'" />
        <GachaPage
          v-else-if="activeView === 'gacha'"
          :accounts="accounts"
          :disabled="loading"
          @manage="goAccounts"
        />
        <AccountsPage
          v-else-if="activeView === 'accounts'"
          :result-source="() => editingConfig.SignFlow?.Result"
        />
      </div>
    </PageSurface>
  </AppPage>
</template>

<style scoped>
.view-nav {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  padding: 12px;
}

.view-tab {
  flex: 0 0 auto;
  padding: 6px 14px;
  font-size: 13px;
  line-height: 20px;
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-quaternary);
  border: 0;
  border-radius: 8px;
  cursor: pointer;
}

.view-tab:hover:not(:disabled) {
  color: var(--ant-color-text);
  background: var(--ant-color-fill-tertiary);
}

.view-tab.is-active {
  color: var(--ant-color-text);
  font-weight: 600;
  background: var(--ant-color-fill-secondary);
  box-shadow: inset 0 -2px var(--ant-color-primary);
}

.view-tab:disabled {
  color: var(--ant-color-text-quaternary);
  cursor: not-allowed;
}

.view-tab:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 1px;
}

.view-body {
  width: 100%;
}

@media (max-width: 860px) {
  .view-nav {
    padding: 8px;
  }
}
</style>
