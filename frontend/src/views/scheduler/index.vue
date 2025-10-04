<template>
  <!-- 主要内容 -->
  <div class="scheduler-main">
    <!-- 页面头部 -->
    <div class="scheduler-header">
      <div class="header-left">
        <h1 class="page-title">调度中心</h1>
      </div>
      <div class="header-actions">
        <a-space size="middle">
          <span class="power-label">任务完成后电源操作：</span>
          <a-select
            v-model:value="powerAction"
            style="width: 140px"
            :disabled="!canChangePowerAction"
            @change="onPowerActionChange"
            size="large"
          >
            <a-select-option
              v-for="(text, signal) in POWER_ACTION_TEXT"
              :key="signal"
              :value="signal"
            >
              {{ text }}
            </a-select-option>
          </a-select>
        </a-space>
      </div>
    </div>

    <!-- 调度台标签页 -->
    <div class="scheduler-tabs">
      <a-tabs
        v-model:activeKey="activeSchedulerTab"
        type="editable-card"
        @edit="onSchedulerTabEdit"
        :hide-add="true"
      >
        <template #tabBarExtraContent>
          <div class="tab-actions">
            <a-tooltip title="添加新的调度台" placement="top">
              <a-button
                class="tab-action-btn tab-add-btn"
                size="default"
                @click="addSchedulerTab"
              >
                <template #icon>
                  <PlusOutlined />
                </template>
              </a-button>
            </a-tooltip>
            <a-tooltip title="删除所有空闲的调度台" placement="top">
              <a-button
                class="tab-action-btn tab-remove-btn"
                size="default"
                @click="removeAllNonRunningTabs"
                :disabled="!hasNonRunningTabs"
                danger
              >
                <template #icon>
                  <MinusOutlined />
                </template>
              </a-button>
            </a-tooltip>
          </div>
        </template>
        <a-tab-pane
          v-for="tab in schedulerTabs"
          :key="tab.key"
          :closable="tab.closable && tab.status !== '运行'"
          :data-tab-key="tab.key"
        >
          <template #tab>
            <span class="tab-title">{{ tab.title }}</span>
            <a-tag :color="TAB_STATUS_COLOR[tab.status]" size="small" class="tab-status">
              {{ tab.status }}
            </a-tag>
            <a-tooltip v-if="tab.status === '运行'" title="运行中的调度台无法删除" placement="top">
              <LockOutlined class="tab-lock-icon" />
            </a-tooltip>
          </template>

          <!-- 任务控制与状态内容 -->
          <div class="task-unified-card" :class="`status-${tab.status}`">
            <!-- 任务控制栏 -->
            <SchedulerTaskControl
              v-model:selectedTaskId="tab.selectedTaskId"
              v-model:selectedMode="tab.selectedMode"
              :taskOptions="taskOptions"
              :taskOptionsLoading="taskOptionsLoading"
              :status="tab.status"
              :disabled="tab.status === '运行'"
              @start="startTask(tab)"
              @stop="stopTask(tab)"
            />

            <!-- 状态展示区域 -->
            <div class="status-container">
              <div class="overview-panel-container">
                <TaskOverviewPanel
                  :ref="el => setOverviewRef(el, tab.key)"
                />
              </div>
              <div class="log-panel-container">
                <SchedulerLogPanel
                  :log-content="tab.lastLogContent"
                  :tab-key="tab.key"
                  :is-log-at-bottom="tab.isLogAtBottom"
                  @scroll="onLogScroll(tab)"
                  @set-ref="setLogRef"
                />
              </div>
            </div>
          </div>
        </a-tab-pane>
        
        <!-- 空状态 -->
        <template #empty>
          <div class="empty-tab-content">
            <a-empty description="暂无调度台" />
          </div>
        </template>
      </a-tabs>
    </div>

    <!-- 消息对话框 -->
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

    <!-- 电源操作倒计时弹窗已移至全局组件 GlobalPowerCountdown.vue -->
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, computed } from 'vue'
import { LockOutlined, MinusOutlined, PlusOutlined } from '@ant-design/icons-vue'
import {
  POWER_ACTION_TEXT,
  TAB_STATUS_COLOR,
} from './schedulerConstants'
import { useSchedulerLogic } from './useSchedulerLogic'
import SchedulerTaskControl from './SchedulerTaskControl.vue'
import SchedulerLogPanel from './SchedulerLogPanel.vue'
import TaskOverviewPanel from './TaskOverviewPanel.vue'

// 使用业务逻辑层
const {
  // 状态
  schedulerTabs,
  activeSchedulerTab,
  taskOptionsLoading,
  taskOptions,
  powerAction,
  messageModalVisible,
  currentMessage,
  messageResponse,

  // 计算属性
  canChangePowerAction,

  // Tab 管理
  addSchedulerTab,
  removeSchedulerTab,
  removeAllNonRunningTabs,

  // 任务操作
  startTask,
  stopTask,

  // 日志操作
  onLogScroll,
  setLogRef,

  // 电源操作
  onPowerActionChange,

  // 消息操作
  sendMessageResponse,
  cancelMessage,

  // 初始化与清理
  initialize,
  loadTaskOptions,
  cleanup,

  // 新增：任务总览面板引用管理
  setOverviewRef,
} = useSchedulerLogic()

// 计算属性：检查是否有可删除的调度台
const hasNonRunningTabs = computed(() => {
  return schedulerTabs.value.some(tab => tab.key !== 'main' && tab.status !== '运行')
})

// Tab 操作
const onSchedulerTabEdit = (targetKey: string | MouseEvent, action: 'add' | 'remove') => {
  if (action === 'add') {
    addSchedulerTab()
  } else if (action === 'remove' && typeof targetKey === 'string') {
    removeSchedulerTab(targetKey)
  }
}


// 生命周期
onMounted(() => {
  initialize() // 初始化TaskManager订阅
  loadTaskOptions()
  
  // 开发环境下导入调试工具
  if (process.env.NODE_ENV === 'development') {
    import('@/utils/scheduler-debug').then(() => {
      console.log('调度中心调试工具已加载，使用 debugScheduler() 和 testWebSocketConnection() 进行调试')
    })
  }
})

onUnmounted(() => {
  cleanup()
})
</script>

<style scoped>
/* 页面容器 */
.scheduler-main {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--ant-color-bg-layout);
}

/* 页面头部样式 */
.scheduler-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
  padding: 0 4px;
}

.header-left {
  flex: 1;
}

.page-title {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.power-label {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin-right: 8px;
}

/* 标签页样式 */
.scheduler-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--ant-color-bg-container);
  border-radius: 8px;
  padding: 12px;
}

.scheduler-tabs :deep(.ant-tabs) {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--ant-color-bg-container);
}

/* 自定义标签页操作按钮 */
.tab-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  margin-top: -12px; /* 负边距抵消容器padding，使按钮上边距与右边距(12px)相同 */
}

.tab-action-btn {
  width: 32px;
  height: 32px;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background-color: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.tab-action-btn:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

.tab-add-btn {
  border-color: var(--ant-color-border);
}

.tab-add-btn:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

.tab-remove-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.tab-remove-btn:disabled:hover {
  border-color: var(--ant-color-border);
  color: var(--ant-color-text-disabled);
}

/* 任务卡片统一容器 */
.task-unified-card {
  background-color: transparent;
  box-shadow: none;
  height: calc(100vh - 237px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 根据状态变化的样式 */
.task-unified-card.status-新建 {
  background-color: transparent;
}

.task-unified-card.status-运行 {
  background-color: transparent;
}

.task-unified-card.status-结束 {
  background-color: transparent;
}

/* 状态容器 */
.status-container {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 16px;
  padding: 0;
  margin: 0;
}

/* 任务总览面板容器 */
.overview-panel-container {
  flex: 0 0 33.333333%; /* 占据1/3宽度 */
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 日志面板容器 */
.log-panel-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 电源操作倒计时弹窗样式已移至 GlobalPowerCountdown.vue */

/* 响应式 - 移动端适配 */
@media (max-width: 768px) {
  .scheduler-main {
    padding: 8px;
  }

  .scheduler-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .header-actions {
    width: 100%;
    justify-content: space-between;
  }

  .power-label {
    display: none;
  }
  
  .status-container {
    flex-direction: column;
  }
  
  .overview-panel-container,
  .log-panel-container {
    flex: 1;
    width: 100%;
  }

  /* 移动端倒计时弹窗适配已移至 GlobalPowerCountdown.vue */
}
</style>