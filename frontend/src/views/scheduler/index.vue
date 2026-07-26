<template>
  <div class="scheduler-main">
    <main class="scheduler-content">
      <MacStatePanel
        v-if="!isSchedulerConnected"
        :type="connectionPanelType"
        :title="SCHEDULER_CONNECTION_STATE_LABEL[schedulerConnectionState]"
        compact
      >
        {{ connectionPanelDescription }}
      </MacStatePanel>

      <!-- 调度台：整页唯一主体。会话 tab 行右侧承载连接状态与全部会话操作 -->
      <div class="scheduler-console">
        <a-tabs
          v-model:active-key="activeSchedulerTab"
          type="editable-card"
          :hide-add="true"
          @edit="onSchedulerTabEdit"
        >
          <template #rightExtra>
            <div class="console-actions">
              <div class="connection-status" aria-live="polite">
                <a-tag :color="SCHEDULER_CONNECTION_STATE_COLOR[schedulerConnectionState]">
                  <template #icon>
                    <WifiOutlined v-if="schedulerConnectionState === 'connected'" />
                    <LoadingOutlined
                      v-else-if="
                        schedulerConnectionState === 'connecting' ||
                        schedulerConnectionState === 'reconnecting'
                      "
                      spin
                    />
                    <DisconnectOutlined v-else />
                  </template>
                  {{ SCHEDULER_CONNECTION_STATE_LABEL[schedulerConnectionState] }}
                </a-tag>
              </div>
              <a-tooltip title="新建调度会话" placement="top">
                <a-button
                  class="header-add-session"
                  type="primary"
                  aria-label="新建调度会话"
                  @click="addSchedulerTab"
                >
                  <template #icon>
                    <PlusOutlined />
                  </template>
                </a-button>
              </a-tooltip>
              <a-button
                class="current-session-delete"
                type="text"
                danger
                :disabled="!currentTabCanRemove"
                @click="removeCurrentSchedulerTab"
              >
                <template #icon>
                  <DeleteOutlined />
                </template>
                删除当前会话
              </a-button>
              <!-- 一键全删：批量移除主调度台以外全部未运行会话，二次确认在逻辑层 -->
              <a-button
                class="clear-all-sessions"
                type="text"
                danger
                @click="removeAllNonRunningTabs"
              >
                <template #icon>
                  <ClearOutlined />
                </template>
                一键全删
              </a-button>
            </div>
          </template>

          <a-tab-pane
            v-for="tab in schedulerTabs"
            :key="tab.key"
            :closable="tab.closable && tab.status !== '运行' && tab.status !== '停止中'"
            :data-tab-key="tab.key"
          >
            <template #tab>
              <div class="tab-content">
                <span class="tab-title">{{ tab.title }}</span>
              </div>
            </template>

            <div class="task-unified-card" :class="`status-${tab.status}`">
              <div v-if="tab.status === '失败'" class="tab-state-panel">
                <MacStatePanel type="error" title="任务执行失败" compact>
                  上次操作未完成。当前任务、模式与日志均已保留，可调整配置后重新执行。
                </MacStatePanel>
              </div>

              <SchedulerTaskControl
                v-model:selected-task-id="tab.selectedTaskId"
                v-model:selected-mode="tab.selectedMode"
                v-model:resume-from-script-id="tab.resumeFromScriptId"
                v-model:running-task-label="tab.runningTaskLabel"
                v-model:running-mode-label="tab.runningModeLabel"
                :resume-script-options="tab.resumeScriptOptions || []"
                :resume-script-loading="tab.resumeScriptLoading"
                :task-options="taskOptions"
                :task-options-loading="taskOptionsLoading"
                :status="tab.status"
                :disabled="tab.status === '运行' || tab.status === '停止中'"
                @task-changed="(taskId: string | null) => handleTaskSelectionChange(tab, taskId)"
                @refresh-resume-scripts="() => loadResumeScriptOptions(tab)"
                @start="onStartTaskClick(tab)"
                @stop="stopTask(tab)"
                @refresh-tasks="loadTaskOptions"
              />

              <div class="status-container">
                <div class="overview-panel-container">
                  <TaskOverviewPanel :ref="el => setOverviewRef(el, tab.key)" />
                </div>
                <div class="log-panel-container">
                  <SchedulerLogPanel
                    :log-content="tab.lastLogContent"
                    :tab-key="tab.key"
                    :is-log-at-bottom="tab.isLogAtBottom"
                    :external-log-mode="tab.logMode"
                    @scroll="(isAtBottom: boolean) => onLogScroll(isAtBottom, tab)"
                    @set-ref="setLogRef"
                  />
                </div>
              </div>
            </div>
          </a-tab-pane>

          <template #empty>
            <div class="empty-tab-content">
              <a-empty description="暂无调度会话">
                <template #description>暂无调度会话</template>
                <a-button type="primary" @click="addSchedulerTab">添加调度会话</a-button>
              </a-empty>
            </div>
          </template>
        </a-tabs>
      </div>
    </main>

    <a-modal
      v-model:open="messageModalVisible"
      :title="currentMessage?.title || '系统消息'"
      @ok="sendMessageResponse"
      @cancel="cancelMessage"
    >
      <div v-if="currentMessage">
        <p>{{ currentMessage.content }}</p>
        <a-input
          v-if="currentMessage.needInput"
          v-model:value="messageResponse"
          placeholder="请输入回复内容"
        />
      </div>
    </a-modal>

    <OverlayRainMask
      v-model="aprilFoolsMaskVisible"
      :opacity="0.75"
      :block-size="128"
      @stopped="onAprilFoolsStopped"
    />
  </div>
</template>

<script lang="ts">
export default {
  name: 'Scheduler', // 用于 keep-alive 识别
}
</script>

<script setup lang="ts">
import { onMounted, onUnmounted, onActivated, onDeactivated, computed, ref } from 'vue'
import {
  ClearOutlined,
  DeleteOutlined,
  PlusOutlined,
  WifiOutlined,
  LoadingOutlined,
  DisconnectOutlined,
} from '@ant-design/icons-vue'
import {
  SCHEDULER_CONNECTION_STATE_LABEL,
  SCHEDULER_CONNECTION_STATE_COLOR,
  type SchedulerTab,
} from './schedulerConstants'
import { useSchedulerLogic } from './useSchedulerLogic'
import SchedulerTaskControl from './SchedulerTaskControl.vue'
import SchedulerLogPanel from './SchedulerLogPanel.vue'
import TaskOverviewPanel from './TaskOverviewPanel.vue'
import OverlayRainMask from '@/components/OverlayRainMask.vue'
import MacStatePanel from '@/components/mac/StatePanel.vue'
const logger = window.electronAPI.getLogger('调度中心')

// 使用业务逻辑层
const {
  // 状态
  schedulerTabs,
  activeSchedulerTab,
  taskOptionsLoading,
  taskOptions,
  messageModalVisible,
  currentMessage,
  messageResponse,
  // Tab 管理
  addSchedulerTab,
  removeSchedulerTab,
  removeAllNonRunningTabs,

  // 任务操作
  startTask,
  stopTask,
  handleTaskSelectionChange,
  loadResumeScriptOptions,

  // 日志操作
  onLogScroll,
  setLogRef,

  // 消息操作
  sendMessageResponse,
  cancelMessage,

  // 初始化与清理
  initialize,
  loadTaskOptions,
  cleanup,

  // 新增：任务总览面板引用管理
  setOverviewRef,

  // 调度器连接状态
  schedulerConnectionState,
  isSchedulerConnected,
} = useSchedulerLogic()

// ==================== 连接状态面板 ====================
const connectionPanelType = computed<'info' | 'warning' | 'error' | 'neutral'>(() => {
  switch (schedulerConnectionState.value) {
    case 'failed':
      return 'error'
    case 'disconnected':
    case 'offline':
      return 'warning'
    case 'connecting':
    case 'reconnecting':
      return 'info'
    default:
      return 'neutral'
  }
})

const connectionPanelDescription = computed(() => {
  switch (schedulerConnectionState.value) {
    case 'connecting':
      return '正在建立实时连接。任务列表仍可查看，运行状态将在连接完成后同步。'
    case 'reconnecting':
      return '实时连接正在恢复。当前会话与日志已保留，请等待状态重新同步。'
    case 'disconnected':
      return '实时连接已断开。当前展示的是最近一次快照，运行与停止结果可能延迟。'
    case 'failed':
      return '无法建立实时连接。请检查后端状态；已选择的任务和现有日志不会被清空。'
    case 'offline':
      return '当前处于离线状态。需要恢复后端连接后才能接收新的调度事件。'
    default:
      return '尚未建立实时连接。初始化完成后会自动同步调度状态。'
  }
})

// ==================== 愚人节彩蛋 ====================
const aprilFoolsMaskVisible = ref(false)
const APRIL_FOOLS_STORAGE_PREFIX = 'scheduler-april-fools-triggered-'

const getUtc8DateParts = () => {
  const now = new Date()
  const utc8 = new Date(now.getTime() + 8 * 60 * 60 * 1000)
  return {
    year: utc8.getUTCFullYear(),
    month: utc8.getUTCMonth() + 1,
    day: utc8.getUTCDate(),
  }
}

const isAprilFoolsDayInUtc8 = () => {
  const { month, day } = getUtc8DateParts()
  return month === 4 && day === 1
}

const getAprilFoolsStorageKey = () => {
  const { year } = getUtc8DateParts()
  return `${APRIL_FOOLS_STORAGE_PREFIX}${year}`
}

const tryTriggerAprilFoolsMask = () => {
  if (!isAprilFoolsDayInUtc8()) return

  const storageKey = getAprilFoolsStorageKey()
  try {
    if (window.localStorage.getItem(storageKey) === '1') return
    window.localStorage.setItem(storageKey, '1')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`读取/写入彩蛋本地标记失败: ${errorMsg}`)
    return
  }

  aprilFoolsMaskVisible.value = true
}

const onStartTaskClick = async (tab: SchedulerTab) => {
  tryTriggerAprilFoolsMask()
  await startTask(tab)
}

const onAprilFoolsStopped = () => {
  logger.info('愚人节彩蛋已触顶停机')
}

// ==================== Tab 操作 ====================
const currentSchedulerTab = computed(() =>
  schedulerTabs.value.find(tab => tab.key === activeSchedulerTab.value)
)

const currentTabCanRemove = computed(() => {
  const tab = currentSchedulerTab.value
  return Boolean(tab && tab.key !== 'main' && tab.status !== '运行' && tab.status !== '停止中')
})

const removeCurrentSchedulerTab = () => {
  if (!currentTabCanRemove.value || !currentSchedulerTab.value) return
  removeSchedulerTab(currentSchedulerTab.value.key)
}

// Tab 操作
const onSchedulerTabEdit = (targetKey: string | MouseEvent, action: 'add' | 'remove') => {
  if (action === 'add') {
    addSchedulerTab()
  } else if (action === 'remove' && typeof targetKey === 'string') {
    removeSchedulerTab(targetKey)
  }
}

// ==================== 生命周期 ====================
onMounted(() => {
  logger.info('调度中心组件首次挂载')
  initialize() // 初始化TaskManager订阅
  loadTaskOptions()

  // 开发环境下导入调试工具
  if (process.env.NODE_ENV === 'development') {
    import('@/utils/scheduler-debug').then(() => {
      logger.info(
        '调度中心调试工具已加载，使用 debugScheduler() 和 testWebSocketConnection() 进行调试'
      )
    })
  }
})

onUnmounted(() => {
  logger.info('调度中心组件卸载')
  cleanup()
})

// keep-alive 生命周期钩子
onActivated(() => {
  logger.info('调度中心组件激活（路由切回）')
})

onDeactivated(() => {
  logger.info('调度中心组件停用（路由切走），但组件保持存活，WebSocket订阅继续运行')
})
</script>

<style scoped>
.scheduler-main {
  container: scheduler-main / inline-size;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--v6-color-background);
}

.connection-status {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.connection-status :deep(.ant-tag) {
  margin-inline-end: 0;
}

.scheduler-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-3);
  min-height: 0;
  overflow: hidden;
  padding: var(--v6-space-4) var(--v6-content-padding-inline);
}

/* 调度台：整页唯一主体，会话 tab 行自带全部操作 */
.scheduler-console {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  container: scheduler-workspace / inline-size;
}

/* tab 行右侧操作区：连接状态 + 新建 + 删当前 + 一键全删 */
.console-actions {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
}

.current-session-delete,
.clear-all-sessions {
  border-radius: var(--v6-radius-control);
}

.header-add-session {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border-radius: var(--v6-radius-control);
}

.scheduler-console :deep(.ant-tabs) {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.scheduler-console :deep(.ant-tabs-content-holder),
.scheduler-console :deep(.ant-tabs-content),
.scheduler-console :deep(.ant-tabs-tabpane) {
  height: 100%;
  min-height: 0;
}

.scheduler-console :deep(.ant-tabs-nav) {
  margin-bottom: var(--v6-space-3);
}

.tab-content {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
}

.tab-title {
  flex-shrink: 0;
}

.task-unified-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-3);
  min-height: 0;
  overflow: hidden;
}

.tab-state-panel {
  flex-shrink: 0;
}

.status-container {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(0, 2fr);
  flex: 1;
  min-height: 0;
  gap: var(--v6-space-3);
}

.overview-panel-container,
.log-panel-container {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

/* 作为子面板根元素的宿主容器:面板根自身的窄屏降级规则
   无法由面板自己声明的容器命中,需由这里的宿主容器驱动 */
.overview-panel-container {
  container: scheduler-overview-host / inline-size;
}

.log-panel-container {
  container: scheduler-log-host / inline-size;
}

.empty-tab-content {
  display: grid;
  place-items: center;
  min-height: 320px;
  padding: var(--v6-space-6);
}

:root[data-perf-mode='low'] .scheduler-main {
  container: scheduler-main / inline-size;
  transition: none;
}

/* 按调度区实际可用宽度切换，导航栏展开时不会把日志与任务面板硬挤。 */
@container scheduler-workspace (max-width: 1050px) {
  .status-container {
    grid-template-columns: 1fr;
    overflow-y: auto;
  }

  .overview-panel-container,
  .log-panel-container {
    min-height: 320px;
  }
}
@container scheduler-main (max-width: 720px) {
  .scheduler-content {
    padding: var(--v6-space-3);
  }
}
</style>
