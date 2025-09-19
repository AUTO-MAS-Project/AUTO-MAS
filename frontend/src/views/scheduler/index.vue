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
        :hide-add="false"
      >
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
          <div class="task-unified-card">
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
            <a-row :gutter="16" class="status-row">
              <!-- 任务队列栏 -->
              <a-col :span="4">
                <SchedulerQueuePanel
                  title="任务队列"
                  :items="tab.taskQueue"
                  type="task"
                  empty-text="暂无任务队列"
                />
              </a-col>

              <!-- 用户队列栏 -->
              <a-col :span="4">
                <SchedulerQueuePanel
                  title="用户队列"
                  :items="tab.userQueue"
                  type="user"
                  empty-text="暂无用户队列"
                />
              </a-col>

              <!-- 日志栏 -->
              <a-col :span="16">
                <SchedulerLogPanel
                  :logs="tab.logs"
                  :tab-key="tab.key"
                  :is-log-at-bottom="tab.isLogAtBottom"
                  @scroll="onLogScroll(tab)"
                  @set-ref="setLogRef"
                  @clear-logs="clearTabLogs(tab)"
                />
              </a-col>
            </a-row>
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

    <!-- 电源操作倒计时模态框 -->
    <a-modal
      v-model:open="powerCountdownVisible"
      title="电源操作确认"
      :closable="false"
      :maskClosable="false"
      @cancel="cancelPowerAction"
    >
      <template #footer>
        <a-button @click="cancelPowerAction">取消</a-button>
      </template>
      <div class="power-countdown">
        <div class="warning-icon">⚠️</div>
        <div>
          <p>
            所有任务已完成，系统将在 <strong>{{ powerCountdown }}</strong> 秒后执行：<strong>{{
              getPowerActionText(powerAction)
            }}</strong>
          </p>
          <a-progress :percent="(10 - powerCountdown) * 10" :show-info="false" />
        </div>
      </div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import {
  getPowerActionText,
  POWER_ACTION_TEXT,
  type SchedulerTab,
  TAB_STATUS_COLOR,
} from './schedulerConstants'
import { useSchedulerLogic } from './useSchedulerLogic'
import SchedulerTaskControl from './SchedulerTaskControl.vue'
import SchedulerQueuePanel from './SchedulerQueuePanel.vue'
import SchedulerLogPanel from './SchedulerLogPanel.vue'

// 使用业务逻辑层
const {
  // 状态
  schedulerTabs,
  activeSchedulerTab,
  taskOptionsLoading,
  taskOptions,
  powerAction,
  powerCountdownVisible,
  powerCountdown,
  messageModalVisible,
  currentMessage,
  messageResponse,

  // 计算属性
  canChangePowerAction,

  // Tab 管理
  addSchedulerTab,
  removeSchedulerTab,

  // 任务操作
  startTask,
  stopTask,

  // 日志操作
  onLogScroll,
  setLogRef,

  // 电源操作
  onPowerActionChange,
  cancelPowerAction,

  // 消息操作
  sendMessageResponse,
  cancelMessage,

  // 初始化与清理
  loadTaskOptions,
  cleanup,
} = useSchedulerLogic()

// Tab 操作
const onSchedulerTabEdit = (targetKey: string | MouseEvent, action: 'add' | 'remove') => {
  if (action === 'add') {
    addSchedulerTab()
  } else if (action === 'remove' && typeof targetKey === 'string') {
    removeSchedulerTab(targetKey)
  }
}

// 清空指定标签页的日志
const clearTabLogs = (tab: SchedulerTab) => {
  tab.logs.splice(0)
}

// 生命周期
onMounted(() => {
  loadTaskOptions()
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
  padding: 16px;
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
}
</style>