<template>
  <!-- 加载状态 -->
  <div v-if="loading" class="loading-container">
    <a-spin size="large" tip="加载中，请稍候..." />
  </div>

  <!-- 主要内容 -->
  <div v-else class="queue-main">
    <!-- 页面头部：统一 MacPageHeader 规范（compact + transparent，动作在右侧） -->
    <MacPageHeader
      class="queue-page-header"
      title="调度队列"
      subtitle="编排队列项与定时设置，控制批量任务的执行顺序"
      compact
      transparent
    >
      <a-space size="middle">
        <a-button type="primary" @click="openQueueCreateDialog">
          <template #icon>
            <PlusOutlined />
          </template>
          新建队列
        </a-button>

        <a-popconfirm
          v-if="queueList.length > 0"
          title="确定要删除这个队列吗？"
          ok-text="确定"
          cancel-text="取消"
          @confirm="handleRemoveQueue(activeQueueId)"
        >
          <a-button danger :disabled="!activeQueueId">
            <template #icon>
              <DeleteOutlined />
            </template>
            删除当前队列
          </a-button>
        </a-popconfirm>
      </a-space>
    </MacPageHeader>

    <!-- 空状态 -->
    <div v-if="!queueList.length || !currentQueueData" class="empty-state">
      <EmptyState
        compact
        title="暂无队列"
        description="创建普通队列或循环队列，开始编排自动化任务。"
      >
        <template #action>
          <a-button type="primary" @click="openQueueCreateDialog">
            <template #icon><PlusOutlined /></template>
            新建队列
          </a-button>
        </template>
      </EmptyState>
    </div>

    <!-- 队列内容 -->
    <div v-else class="queue-content">
      <section class="queue-workspace">
        <div class="queue-selector-bar">
          <div class="queue-selector-label">
            <span>队列选择</span>
            <a-tag :color="queueList.length > 0 ? 'success' : 'default'">
              {{ queueList.length }} 个队列
            </a-tag>
          </div>
          <nav class="queue-buttons-container" aria-label="选择调度队列">
            <button
              v-for="queue in queueList"
              :key="queue.id"
              type="button"
              class="queue-button"
              :class="{ 'queue-button--active': activeQueueId === queue.id }"
              :aria-current="activeQueueId === queue.id ? 'true' : undefined"
              @click="onQueueChange(queue.id)"
            >
              {{ queue.name }}
            </button>
          </nav>
        </div>

        <header class="queue-config-header">
          <div class="queue-title-container">
            <div v-if="!isEditingQueueName" class="queue-title-display">
              <span class="queue-title-text">{{ currentQueueName || '队列配置' }}</span>
              <a-button type="text" size="small" class="queue-edit-btn" @click="startEditQueueName">
                <template #icon>
                  <EditOutlined />
                </template>
              </a-button>
            </div>
            <div v-else class="queue-title-edit">
              <a-input
                ref="queueNameInputRef"
                v-model:value="currentQueueName"
                placeholder="请输入队列名称"
                class="queue-title-input"
                :maxlength="50"
                @blur="finishEditQueueName"
                @press-enter="finishEditQueueName"
              />
            </div>
          </div>
        </header>

        <div class="queue-config-content">
          <!-- 队列开关配置 -->
          <div class="config-section">
            <div class="config-grid">
              <div class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">启动时运行</span>
                  <a-tooltip title="软件启动时自动运行此队列">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <a-select
                  v-model:value="currentStartUpEnabled"
                  style="width: 100%"
                  @change="(value: any) => handleConfigChange('StartUpEnabled', value)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </div>
              <div class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">定时运行</span>
                  <a-tooltip title="在设定的时间自动运行此队列">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <a-select
                  v-model:value="currentTimeEnabled"
                  style="width: 100%"
                  @change="(value: any) => handleConfigChange('TimeEnabled', value)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </div>
              <div class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">循环运行</span>
                  <a-tooltip title="按每个队列项的循环调度设置持续运行；启用后运行中的队列禁止编辑">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <a-select
                  v-model:value="currentCycleEnabled"
                  style="width: 100%"
                  @change="(value: any) => handleConfigChange('CycleEnabled', value)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </div>
              <div class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">完成后操作</span>
                  <a-tooltip title="队列完成后执行的操作">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <a-select
                  v-model:value="currentAfterAccomplish"
                  style="width: 100%"
                  :options="afterAccomplishOptions"
                  placeholder="请选择操作"
                  @change="(value: any) => handleConfigChange('AfterAccomplish', value)"
                />
              </div>
            </div>
          </div>

          <!-- 定时项管理 -->
          <a-col :span="24" class="manager-col">
            <TimeSetManager
              v-if="activeQueueId && currentQueueData"
              :queue-id="activeQueueId"
              :time-sets="currentTimeSets"
              style="font-size: 14px"
              @refresh="refreshTimeSets"
            />
          </a-col>

          <!-- 队列项管理 -->
          <a-col :span="24" class="manager-col">
            <QueueItemManager
              v-if="activeQueueId && currentQueueData"
              :queue-id="activeQueueId"
              :queue-items="currentQueueItems"
              :cycle-enabled="currentCycleEnabled"
              style="font-size: 14px"
              @refresh="refreshQueueItems"
            />
          </a-col>
        </div>
      </section>
    </div>
  </div>

  <a-modal
    v-model:open="queueCreateDialogOpen"
    title="选择队列类型"
    ok-text="创建队列"
    cancel-text="取消"
    :confirm-loading="queueCreating"
    :closable="!queueCreating"
    :mask-closable="!queueCreating"
    @ok="confirmQueueCreate"
  >
    <a-radio-group v-model:value="selectedQueueType" class="queue-type-options">
      <a-radio-button value="normal" class="queue-type-option">
        <span class="queue-type-title">普通队列</span>
        <span class="queue-type-description">按队列顺序执行一次，适合手动或定时任务。</span>
      </a-radio-button>
      <a-radio-button value="cycle" class="queue-type-option">
        <span class="queue-type-title">循环队列</span>
        <span class="queue-type-description">启用循环调度，按每个队列项的周期持续运行。</span>
      </a-radio-button>
    </a-radio-group>
  </a-modal>
</template>

<script setup lang="ts">
import QueueItemManager from '@/views/queue/components/QueueItemManager.vue'
import TimeSetManager from '@/views/queue/components/TimeSetManager.vue'
import EmptyState from '@/components/v6/EmptyState.vue'
import MacPageHeader from '@/components/mac/PageHeader.vue'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { onMounted, onUnmounted, ref } from 'vue'
import { useQueueLogic } from './useQueueLogic'

type QueueCreationType = 'normal' | 'cycle'

const {
  queueList,
  activeQueueId,
  currentQueueData,
  currentQueueName,
  currentStartUpEnabled,
  currentTimeEnabled,
  currentCycleEnabled,
  currentAfterAccomplish,
  isEditingQueueName,
  currentTimeSets,
  currentQueueItems,
  loading,
  afterAccomplishOptions,
  refreshTimeSets,
  refreshQueueItems,
  startEditQueueName,
  finishEditQueueName,
  handleConfigChange,
  handleAddQueue,
  handleRemoveQueue,
  onQueueChange,
  initialize,
  cleanup,
} = useQueueLogic()

const queueCreateDialogOpen = ref(false)
const queueCreating = ref(false)
const selectedQueueType = ref<QueueCreationType>('normal')

const openQueueCreateDialog = () => {
  selectedQueueType.value = 'normal'
  queueCreateDialogOpen.value = true
}

const confirmQueueCreate = async () => {
  if (queueCreating.value) return
  queueCreating.value = true
  try {
    const created = await handleAddQueue(selectedQueueType.value === 'cycle')
    if (created) queueCreateDialogOpen.value = false
  } finally {
    queueCreating.value = false
  }
}

onMounted(async () => {
  await initialize()
})

onUnmounted(() => {
  cleanup()
})
</script>

<style scoped>
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 240px;
}

.queue-main {
  min-width: 0;
  margin: 0 auto;
  background: transparent;
  container: queue-page / inline-size;
}

/* 页面头部：页面容器自带内边距，抵消 PageHeader 的全宽内边距保持对齐 */
.queue-page-header {
  margin-bottom: var(--v6-space-4);
}

.queue-page-header :deep(.mac-page-header) {
  padding-inline: 4px;
}

/* 空状态 */
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 240px;
  padding: var(--v6-space-6);
  background: var(--v6-color-surface-transparent);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  margin: var(--v6-space-4) 0;
  backdrop-filter: var(--v6-backdrop-vibrancy);
}

/* 队列内容 */
.queue-content {
  min-width: 0;
}

/* 一个连续工作区承载队列选择、策略与内容，避免每段再套独立卡片。 */
.queue-workspace {
  overflow: hidden;
  background: var(--v6-color-surface-transparent);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.queue-selector-bar {
  display: flex;
  align-items: center;
  gap: var(--v6-space-4);
  min-height: 60px;
  padding: 10px var(--v6-space-4);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.queue-selector-label {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--v6-space-2);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  font-weight: 600;
}

.queue-buttons-container {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  gap: 6px;
}

.queue-button {
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  color: var(--v6-color-text-secondary);
  font: inherit;
  cursor: pointer;
  transition:
    color var(--v6-motion-fast) var(--v6-ease-out),
    background var(--v6-motion-fast) var(--v6-ease-out),
    border-color var(--v6-motion-fast) var(--v6-ease-out);
}

.queue-button:hover {
  color: var(--v6-color-text);
  background: var(--v6-vibrancy-hover);
}

.queue-button--active {
  border-color: color-mix(in srgb, var(--v6-color-primary) 22%, transparent);
  background: color-mix(in srgb, var(--v6-color-primary) 12%, transparent);
  color: var(--v6-color-primary);
  font-weight: 600;
}

.queue-button:focus-visible {
  outline: none;
  box-shadow: var(--v6-focus-ring);
}

.queue-config-panel {
  display: flex;
  flex-direction: column;
}

.queue-config-header {
  min-height: 48px;
  display: flex;
  align-items: center;
  padding: 0 var(--v6-space-5);
}

.queue-config-content {
  display: flex;
  flex-direction: column;
  padding: 0 var(--v6-space-5) var(--v6-space-4);
}

.queue-title-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0;
}

.queue-title-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.queue-title-text {
  font-size: var(--v6-font-size-lg);
  font-weight: 600;
  color: var(--ant-color-text);
}

.queue-edit-btn {
  color: var(--ant-color-primary);
  padding: 0;
}

.queue-title-input {
  flex: 1;
  max-width: 400px;
  border-radius: var(--v6-radius-control);
  transition: all 0.2s ease;
}

.config-section {
  padding: var(--v6-space-4) 0 var(--v6-space-5);
  border-top: 1px solid var(--v6-color-border-subtle);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

/* 开关配置网格:按 queue-page 容器宽度响应(替代视口栅格 a-col),
   宽容器 4 列 / 中容器 2 列 / 窄容器 1 列 */
.config-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px 16px;
}

@container queue-page (max-width: 1200px) {
  .config-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@container queue-page (max-width: 576px) {
  .config-grid {
    grid-template-columns: 1fr;
  }
}

.manager-col {
  display: flex;
  flex-direction: column;
  margin-top: var(--v6-space-3);
}

.form-item-vertical {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 0;
}

.form-label-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-label {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--v6-color-text-tertiary);
  font-size: 14px;
}

.queue-type-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v6-space-3, 12px);
  width: 100%;
}

.queue-type-option {
  display: flex;
  height: auto;
  min-height: 104px;
  align-items: flex-start;
  padding: var(--v6-space-4, 16px);
  border: 1px solid var(--v6-color-border-subtle) !important;
  border-radius: var(--v6-radius-control, 8px) !important;
  background: var(--v6-color-surface-transparent);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  white-space: normal;
}

.queue-type-option::before {
  display: none !important;
}

.queue-type-option.ant-radio-button-wrapper-checked {
  border-color: var(--v6-color-primary) !important;
  background: var(--ant-color-primary-bg);
  box-shadow: 0 0 0 1px var(--v6-color-primary);
}

.queue-type-option :deep(> span:last-child) {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-1, 4px);
}

.queue-type-title {
  color: var(--ant-color-text);
  font-size: var(--v6-font-size-base, 14px);
  font-weight: var(--v6-font-weight-semibold, 600);
}

.queue-type-description {
  color: var(--ant-color-text-secondary);
  font-size: var(--v6-font-size-sm, 13px);
  line-height: 1.6;
}

/* 以实际内容区宽度响应：侧栏展开时也不会把布局误判成宽屏。
   页头自身的窄屏换行由 MacPageHeader 内置容器查询处理。 */
@container queue-page (max-width: 640px) {
  .queue-selector-bar,
  .queue-config-header,
  .queue-config-content {
    padding-inline: var(--v6-space-3);
  }

  .queue-selector-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .queue-type-options {
    grid-template-columns: 1fr;
  }

  .queue-title-input {
    width: 100%;
    max-width: none;
  }
}

.queue-title-input :deep(.ant-input) {
  font-size: 16px;
  font-weight: 500;
}

.queue-title-input :deep(.ant-input:focus-visible) {
  box-shadow: var(--v6-focus-ring-inset);
}
</style>
