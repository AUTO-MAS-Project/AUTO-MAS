<script setup lang="ts">
/**
 * Lane 8：工具页异步任务状态面板。
 *
 * 显示当前任务的 running/success/failure/cancelled 状态、进度、错误原因，
 * 并提供取消、重试和关闭按钮。
 */
import { computed } from 'vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  StopOutlined,
  ReloadOutlined,
  CloseOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons-vue'
import type { AsyncTaskStatus, AsyncTaskProgress } from '@/composables/useToolsAsyncTask'

const props = defineProps<{
  status: AsyncTaskStatus
  error: string | null
  progress: AsyncTaskProgress | null
  taskName: string
  canCancel: boolean
  canRetry: boolean
  progressPercent: number
}>()

const emit = defineEmits<{
  cancel: []
  retry: []
  dismiss: []
}>()

const statusConfig = computed(() => {
  switch (props.status) {
    case 'running':
      return {
        icon: LoadingOutlined,
        color: 'var(--ant-color-primary)',
        bgColor: 'var(--ant-color-primary-bg)',
        borderColor: 'var(--ant-color-primary-border)',
        label: '进行中',
        spin: true,
      }
    case 'success':
      return {
        icon: CheckCircleOutlined,
        color: 'var(--ant-color-success)',
        bgColor: 'var(--ant-color-success-bg)',
        borderColor: 'var(--ant-color-success-border)',
        label: '已完成',
        spin: false,
      }
    case 'failure':
      return {
        icon: CloseCircleOutlined,
        color: 'var(--ant-color-error)',
        bgColor: 'var(--ant-color-error-bg)',
        borderColor: 'var(--ant-color-error-border)',
        label: '失败',
        spin: false,
      }
    case 'cancelled':
      // Lane 8：签到等任务的"取消"实际上只是停止前端等待结果，
      // 后端 HTTP 请求无法真正中断。文案必须明确这一点，避免误导用户。
      return {
        icon: StopOutlined,
        color: 'var(--ant-color-text-secondary)',
        bgColor: 'var(--ant-color-fill-quaternary)',
        borderColor: 'var(--ant-color-border-secondary)',
        label: '已停止等待',
        spin: false,
      }
    default:
      return null
  }
})

const showPanel = computed(() => props.status !== 'idle' && statusConfig.value !== null)

const progressText = computed(() => {
  if (!props.progress) return ''
  const { current, total, currentLabel } = props.progress
  const base = `${current} / ${total}`
  return currentLabel ? `${base} · ${currentLabel}` : base
})

const showActions = computed(
  () => props.status === 'success' || props.status === 'failure' || props.status === 'cancelled'
)
</script>

<template>
  <div
    v-if="showPanel && statusConfig"
    class="tools-task-panel"
    :style="{
      backgroundColor: statusConfig.bgColor,
      borderColor: statusConfig.borderColor,
    }"
  >
    <div class="panel-main">
      <div class="panel-icon-area">
        <component
          :is="statusConfig.icon"
          :spin="statusConfig.spin"
          :style="{ color: statusConfig.color }"
        />
      </div>
      <div class="panel-content">
        <div class="panel-header-row">
          <span class="panel-task-name">{{ taskName }}</span>
          <a-tag
            :style="{ color: statusConfig.color, borderColor: statusConfig.borderColor }"
            :bordered="false"
          >
            {{ statusConfig.label }}
          </a-tag>
        </div>
        <!-- 进度条 -->
        <div v-if="status === 'running' && progress" class="panel-progress">
          <a-progress
            :percent="progressPercent"
            :show-info="false"
            size="small"
            :stroke-color="statusConfig.color"
          />
          <span class="progress-text">{{ progressText }}</span>
        </div>
        <!-- 错误原因 -->
        <div v-if="status === 'failure' && error" class="panel-error">
          <ExclamationCircleOutlined class="error-icon" />
          <span class="error-text">{{ error }}</span>
        </div>
        <!-- 取消提示 -->
        <div v-if="status === 'cancelled'" class="panel-info">
          <span class="info-text"> 已停止等待结果（后端可能仍在执行，请勿立即重复触发）。 </span>
        </div>
      </div>
    </div>
    <div class="panel-actions">
      <a-button v-if="canCancel" size="small" danger @click="emit('cancel')">
        <template #icon><StopOutlined /></template>
        取消
      </a-button>
      <a-button v-if="canRetry" size="small" type="primary" ghost @click="emit('retry')">
        <template #icon><ReloadOutlined /></template>
        重试
      </a-button>
      <a-button v-if="showActions" size="small" type="text" @click="emit('dismiss')">
        <template #icon><CloseOutlined /></template>
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.tools-task-panel {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid;
  margin-bottom: 16px;
}

.panel-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.panel-icon-area {
  font-size: 20px;
  line-height: 1;
  padding-top: 2px;
}

.panel-content {
  flex: 1;
  min-width: 0;
}

.panel-header-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.panel-task-name {
  font-weight: 600;
  font-size: 14px;
  color: var(--ant-color-text);
}

.panel-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}

.panel-progress :deep(.ant-progress) {
  flex: 1;
  min-width: 100px;
}

.progress-text {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
  font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
}

.panel-error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 6px;
  font-size: 13px;
  color: var(--ant-color-error);
  line-height: 1.5;
}

.error-icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.error-text {
  word-break: break-word;
}

.panel-info {
  margin-top: 6px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

@media (max-width: 640px) {
  .tools-task-panel {
    flex-direction: column;
  }

  .panel-actions {
    align-self: flex-end;
  }
}

@media (prefers-reduced-motion: reduce) {
  .panel-progress :deep(.ant-progress-inner) {
    transition: none;
  }
}
</style>
