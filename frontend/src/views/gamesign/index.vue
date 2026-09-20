<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ToolsConfig, ToolsConfig_GameSign } from '@/api'
import { useToolsApi } from '@/composables/useToolsApi'
import { useToolsStatusPolling } from '@/composables/useToolsStatusPolling'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_GAMESIGN_RESULT_UPDATED,
  WS_ID_GAME_SIGN,
  type WSGameSignResultData,
} from '@/services/websocket/types'
import CommunityActivityView from './CommunityActivityView.vue'
import TabGameSign from './TabGameSign.vue'

const { t } = useI18n()

defineOptions({ name: 'GameSignPage' })

const logger = window.electronAPI.getLogger('游戏社区')
const route = useRoute()
const router = useRouter()

type CommunityTab = 'sign' | 'activity'

const { loading, getTools, updateTools } = useToolsApi()
const { subscribe, unsubscribe } = useWebSocket()

// 工具数据（保留完整 ToolsConfig，避免更新时覆盖其它工具的配置）
const toolsConfig = reactive<ToolsConfig>({
  GameSign: {
    Enabled: false,
    NotifyEnabled: false,
    ActivityEnabled: true,
    RunOnStartup: false,
    LastSignDate: '2000-01-01',
    Status: '-',
    Result: '{}',
  },
})

// 本地编辑状态
const editingConfig = reactive<ToolsConfig>({
  GameSign: {
    Enabled: false,
    NotifyEnabled: false,
    ActivityEnabled: true,
    RunOnStartup: false,
    LastSignDate: '2000-01-01',
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

const activeTab = computed<CommunityTab>(() =>
  route.query.tab === 'activity' && activityEnabled.value ? 'activity' : 'sign'
)

const handleTabChange = (key: string | number) => {
  const tab: CommunityTab = key === 'activity' && activityEnabled.value ? 'activity' : 'sign'
  void router.replace({
    path: '/gamesign',
    query: tab === 'activity' ? { tab: 'activity' } : {},
  })
}

const syncGameSignResult = (result: unknown) => {
  if (!isMounted || typeof result !== 'string') return
  if (toolsConfig.GameSign) {
    toolsConfig.GameSign.Result = result
  }
  if (editingConfig.GameSign) {
    editingConfig.GameSign.Result = result
  }
}

// 状态轮询：签到页签激活时才拉；签到已启用 5 s 一次，否则 30 s
const { updateStatus, startStatusPolling, stopStatusPolling } = useToolsStatusPolling({
  applyStatus: data => {
    if (data.GameSign?.Status) {
      toolsConfig.GameSign!.Status = data.GameSign.Status
    }
    syncGameSignResult(data.GameSign?.Result)
  },
  isActive: () => toolsConfig.GameSign?.Enabled === true,
  enabled: () => activeTab.value === 'sign',
  invalidMessage: () => t('gamesign.statusInvalid'),
  logger,
})

// 签到完成后立即刷新配置（不等轮询）
const refreshGameSignConfig = () => updateStatus()

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
        LastSignDate: '2000-01-01',
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

watch(activeTab, tab => {
  if (tab === 'sign' && isMounted) void updateStatus()
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
  <div class="gamesign-container">
    <div class="gamesign-header">
      <h1 class="page-title">{{ t('gamesign.title') }}</h1>
    </div>
    <div class="gamesign-content">
      <a-tabs :active-key="activeTab" type="card" class="community-tabs" @change="handleTabChange">
        <a-tab-pane key="sign" :tab="t('gamesign.nav.sign')">
          <TabGameSign
            v-if="editingConfig.GameSign"
            :config="editingConfig.GameSign"
            :disabled="loading"
            :on-field-change="handleGameSignFieldChange"
            :on-refresh-config="refreshGameSignConfig"
          />
        </a-tab-pane>
        <a-tab-pane v-if="activityEnabled" key="activity" :tab="t('gamesign.nav.activity')">
          <CommunityActivityView />
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<style scoped>
/* 与工具/设置页统一的页面布局与内容卡片样式 */
.gamesign-container {
  width: 100%;
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.gamesign-header {
  margin-bottom: 16px;
  padding: 0 4px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.gamesign-content {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  width: 100%;
  flex: 1;
}

.community-tabs {
  margin: 0;
  padding: 12px;
}

.community-tabs :deep(.ant-tabs-nav) {
  margin: 0;
  padding: 0;
}

.community-tabs :deep(.ant-tabs-content-holder) {
  overflow: visible;
}

.community-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab) {
  margin-right: 8px;
  background: transparent;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px 8px 0 0;
}

.community-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab-active) {
  background: var(--ant-color-bg-container);
  border-bottom-color: var(--ant-color-bg-container);
}

/* ==================== 子组件统一表单样式（与工具页/设置页一致） ==================== */
:deep(.tab-content) {
  padding: 24px;
  width: 100%;
}

:deep(.form-section) {
  margin-bottom: 32px;
}

:deep(.form-section:last-child) {
  margin-bottom: 0;
}

:deep(.section-header) {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

:deep(.section-header h3) {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

:deep(.section-header h3::before) {
  content: '';
  width: 4px;
  height: 24px;
  background: var(--ant-color-primary);
  border-radius: 2px;
}

:deep(.section-description) {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

:deep(.form-item-vertical) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

:deep(.form-label-wrapper) {
  display: flex;
  align-items: center;
  gap: 8px;
}

:deep(.form-label) {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

:deep(.help-icon) {
  color: #8c8c8c;
  font-size: 14px;
}

@media (max-width: 860px) {
  .community-tabs {
    padding: 8px;
  }

  :deep(.tab-content) {
    padding: 16px;
  }

  :deep(.section-header) {
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 12px;
  }
}
</style>
