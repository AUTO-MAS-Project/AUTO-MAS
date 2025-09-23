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

    <!-- 电源操作倒计时全屏弹窗 -->
    <div v-if="powerCountdownVisible" class="power-countdown-overlay">
      <div class="power-countdown-container">
        <div class="countdown-content">
          <div class="warning-icon">⚠️</div>
          <h2 class="countdown-title">{{ powerCountdownData.title || `${getPowerActionText(powerAction)}倒计时` }}</h2>
          <p class="countdown-message">
            {{ powerCountdownData.message || `程序将在倒计时结束后执行 ${getPowerActionText(powerAction)} 操作` }}
          </p>
          <div class="countdown-timer" v-if="powerCountdownData.countdown !== undefined">
            <span class="countdown-number">{{ powerCountdownData.countdown }}</span>
            <span class="countdown-unit">秒</span>
          </div>
          <div class="countdown-timer" v-else>
            <span class="countdown-text">等待后端倒计时...</span>
          </div>
          <a-progress 
            v-if="powerCountdownData.countdown !== undefined"
            :percent="Math.max(0, Math.min(100, (60 - powerCountdownData.countdown) / 60 * 100))" 
            :show-info="false" 
            :stroke-color="(powerCountdownData.countdown || 0) <= 10 ? '#ff4d4f' : '#1890ff'"
            :stroke-width="8"
            class="countdown-progress"
          />
          <div class="countdown-actions">
            <a-button 
              type="primary" 
              size="large" 
              @click="cancelPowerAction"
              class="cancel-button"
            >
              取消操作
            </a-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { LockOutlined } from '@ant-design/icons-vue'
import {
  getPowerActionText,
  POWER_ACTION_TEXT,
  type SchedulerTab,
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
  powerCountdownVisible,
  powerCountdownData,
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
  initialize,
  loadTaskOptions,
  cleanup,

  // 新增：任务总览面板引用管理
  setOverviewRef,
} = useSchedulerLogic()

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

/* 任务卡片统一容器 */
.task-unified-card {
  background-color: transparent;
  box-shadow: none;
  height: calc(100vh - 230px); /* 动态计算高度 */
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

/* 电源操作倒计时全屏弹窗样式 */
.power-countdown-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.8);
  backdrop-filter: blur(8px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.3s ease-out;
}

.power-countdown-container {
  background: var(--ant-color-bg-container);
  border-radius: 16px;
  padding: 48px;
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.2);
  text-align: center;
  max-width: 500px;
  width: 90%;
  animation: slideIn 0.3s ease-out;
}

.countdown-content .warning-icon {
  font-size: 64px;
  margin-bottom: 24px;
  display: block;
  animation: pulse 2s infinite;
}

.countdown-title {
  font-size: 28px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0 0 16px 0;
}

.countdown-message {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 32px 0;
  line-height: 1.5;
}

.countdown-timer {
  display: flex;
  align-items: baseline;
  justify-content: center;
  margin-bottom: 32px;
}

.countdown-number {
  font-size: 72px;
  font-weight: 700;
  color: var(--ant-color-primary);
  line-height: 1;
  margin-right: 8px;
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
}

.countdown-unit {
  font-size: 24px;
  color: var(--ant-color-text-secondary);
  font-weight: 500;
}

.countdown-text {
  font-size: 24px;
  color: var(--ant-color-text-secondary);
  font-weight: 500;
}

.countdown-progress {
  margin-bottom: 32px;
}

.countdown-actions {
  display: flex;
  justify-content: center;
}

.cancel-button {
  padding: 12px 32px;
  height: auto;
  font-size: 16px;
  font-weight: 500;
}

/* 动画效果 */
@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(-20px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.1);
  }
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
  
  .status-container {
    flex-direction: column;
  }
  
  .overview-panel-container,
  .log-panel-container {
    flex: 1;
    width: 100%;
  }

  /* 移动端倒计时弹窗适配 */
  .power-countdown-container {
    padding: 32px 24px;
    margin: 16px;
  }

  .countdown-title {
    font-size: 24px;
  }

  .countdown-number {
    font-size: 56px;
  }

  .countdown-unit {
    font-size: 20px;
  }

  .countdown-content .warning-icon {
    font-size: 48px;
    margin-bottom: 16px;
  }
}
</style>