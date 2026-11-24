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
import { PlusOutlined, SwapOutlined } from '@ant-design/icons-vue'
import type { ToolsConfig_GameSign } from '@/api'
import { useToolsApi, type ToolsViewConfig } from '@/composables/useToolsApi'
import { useToolsStatusPolling } from '@/composables/useToolsStatusPolling'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_GAMESIGN_RESULT_UPDATED,
  WS_ID_GAME_SIGN,
  type WSGameSignResultData,
} from '@/services/websocket/types'
import { AppPage, PageHeader, PageSurface } from '@/components/ui'
import AccountsPage from './AccountsPage.vue'
import CommunityActivityView from './CommunityActivityView.vue'
import GachaPage from './GachaPage.vue'
import SignHomePage from './SignHomePage.vue'
import { useGameSignAccounts } from './useGameSignAccounts'
import { useManualSign } from './useManualSign'

const { t } = useI18n()

defineOptions({ name: 'GameSignPage' })

const logger = window.electronAPI.getLogger('游戏社区')
const route = useRoute()
const router = useRouter()

type CommunityView = 'sign' | 'activity' | 'gacha' | 'accounts'

const VIEW_KEYS: readonly CommunityView[] = ['sign', 'activity', 'gacha', 'accounts']

/** 导航文案显式列出：动态拼接的 key 无法被 i18n 审计识别 */
const VIEW_LABELS: Record<CommunityView, string> = {
  sign: 'core.gamesign.nav.sign',
  activity: 'core.gamesign.nav.activity',
  gacha: 'core.gamesign.nav.gacha',
  accounts: 'core.gamesign.nav.accounts',
}

const { loading, getTools, updateTools } = useToolsApi()
const { subscribe, unsubscribe } = useWebSocket()

// 工具数据（保留完整 ToolsConfig，避免更新时覆盖其它工具的配置）
const toolsConfig = reactive<ToolsViewConfig>({
  GameSign: {
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
  GameSign: {
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

let gameSignSubscriptionId: string | null = null

// 卸载守卫：组件卸载后阻止异步回调写入响应式状态
let isMounted = true

const activityEnabled = computed(
  () => toolsLoaded.value && editingConfig.GameSign?.ActivityEnabled !== false
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
    path: '/gamesign',
    query: view === 'sign' ? {} : { tab: view },
  })
}

const {
  accounts,
  signResult,
  load: loadAccounts,
} = useGameSignAccounts(() => editingConfig.GameSign?.Result)

const refreshGameSignConfig = () => updateStatus()

const { signLoading, run: runManualSign } = useManualSign(async () => {
  await refreshGameSignConfig()
  await loadAccounts()
})

const syncGameSignResult = (result: unknown) => {
  if (!isMounted || typeof result !== 'string') return
  if (toolsConfig.GameSign) {
    toolsConfig.GameSign.Result = result
  }
  if (editingConfig.GameSign) {
    editingConfig.GameSign.Result = result
  }
}

// 状态轮询：签到视图激活时才拉；签到已启用 5 s 一次，否则 30 s
const { updateStatus, startStatusPolling, stopStatusPolling } = useToolsStatusPolling({
  applyStatus: data => {
    if (data.GameSign?.Status) {
      toolsConfig.GameSign!.Status = data.GameSign.Status
    }
    // 「上次签到」是只读展示字段，必须跟随轮询刷新：手动签到或凭据变更后
    // 后端会重写甚至重置该日期，只在挂载时读一次会一直显示旧值。
    if (data.GameSign?.LastSignDate) {
      toolsConfig.GameSign!.LastSignDate = data.GameSign.LastSignDate
      if (editingConfig.GameSign) {
        editingConfig.GameSign.LastSignDate = data.GameSign.LastSignDate
      }
    }
    syncGameSignResult(data.GameSign?.Result)
  },
  isActive: () => toolsConfig.GameSign?.Enabled === true,
  enabled: () => activeView.value === 'sign',
  invalidMessage: () => t('core.gamesign.statusInvalid'),
  logger,
})

// 加载配置
const loadTools = async () => {
  try {
    const data = await getTools()
    if (!data.GameSign) {
      data.GameSign = {
        Enabled: false,
        NotifyEnabled: false,
        ActivityEnabled: true,
        RunOnStartup: false,
        LastSignDate: '2000-01-01T00:00:00+08:00',
        Status: '-',
        Result: '{}',
      }
    }
    data.GameSign.ActivityEnabled ??= true
    Object.assign(toolsConfig, data)
    Object.assign(editingConfig, JSON.parse(JSON.stringify(data)))
    toolsLoaded.value = true
    logger.info('游戏社区配置加载完成')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载游戏社区配置失败: ${errorMsg}`)
  }
}

// 只提交当前 GameSign 字段，避免并发覆盖签到状态或其它工具配置。
type GameSignFieldKey = keyof ToolsConfig_GameSign

const handleGameSignFieldChange = async <K extends GameSignFieldKey>(
  key: K,
  value: ToolsConfig_GameSign[K]
) => {
  const editingGameSign = editingConfig.GameSign
  if (!editingGameSign) return

  const previousValue = editingGameSign[key]

  try {
    editingGameSign[key] = value
    await updateTools({
      GameSign: { [key]: value } as Partial<ToolsConfig_GameSign>,
    })

    if (toolsConfig.GameSign && key !== 'Status' && key !== 'Result') {
      toolsConfig.GameSign[key] = value
    }

    logger.info(`GameSign.${key} 已保存`)
  } catch (error) {
    // 仅在当前值仍是本次提交值时回滚，避免较早请求失败覆盖更新后的操作。
    if (editingGameSign[key] === value) {
      editingGameSign[key] = previousValue
    }
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 GameSign.${key} 失败: ${errorMsg}`)
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
    void router.replace({ path: '/gamesign', query: {} })
  }
})

onMounted(async () => {
  gameSignSubscriptionId = subscribe(
    { id: WS_ID_GAME_SIGN, type: WS_GAMESIGN_RESULT_UPDATED },
    wsMessage => {
      const data = wsMessage.data as unknown as WSGameSignResultData
      syncGameSignResult(data.result)
    }
  )
  await loadTools()
  await loadAccounts()
  startStatusPolling()
})

onUnmounted(() => {
  isMounted = false
  stopStatusPolling()
  if (gameSignSubscriptionId) {
    unsubscribe(gameSignSubscriptionId)
    gameSignSubscriptionId = null
  }
})
</script>

<template>
  <AppPage layout="scroll">
    <PageHeader :title="t('core.gamesign.title')" :subtitle="t('core.gamesign.subtitle')">
      <template #actions>
        <a-button :disabled="loading" @click="goAccounts">
          <template #icon><PlusOutlined /></template>
          {{ t('core.gamesign.nav.accounts') }}
        </a-button>
        <a-button
          type="primary"
          :loading="signLoading"
          :disabled="loading || !editingConfig.GameSign?.Enabled"
          @click="runManualSign"
        >
          <template #icon><SwapOutlined /></template>
          {{ t('core.gamesign.section.signAll') }}
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
        <SignHomePage
          v-if="activeView === 'sign' && editingConfig.GameSign"
          :config="editingConfig.GameSign"
          :result="signResult"
          :accounts="accounts"
          :disabled="loading"
          :sign-loading="signLoading"
          :on-field-change="handleGameSignFieldChange"
          @manage="goAccounts"
          @sign="runManualSign"
          @refresh="refreshGameSignConfig"
        />
        <CommunityActivityView v-else-if="activeView === 'activity'" />
        <GachaPage v-else-if="activeView === 'gacha'" @back="handleViewChange('sign')" />
        <AccountsPage
          v-else-if="activeView === 'accounts'"
          :result-source="() => editingConfig.GameSign?.Result"
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
