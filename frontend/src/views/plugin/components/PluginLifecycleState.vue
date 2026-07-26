<template>
  <div class="plugin-lifecycle-state" :data-status="status">
    <div class="lifecycle-header">
      <a-tag :color="statusColor" class="lifecycle-tag">
        {{ statusLabel }}
      </a-tag>
      <a-tag v-if="phaseLabel" :color="phaseColor" class="lifecycle-phase-tag">
        {{ phaseLabel }}
      </a-tag>
    </div>

    <a-descriptions v-if="showDetails" :column="2" size="small" class="lifecycle-details">
      <a-descriptions-item label="运行状态">
        <a-tag :color="statusTagColor">
          {{ statusLabel }}
        </a-tag>
      </a-descriptions-item>
      <a-descriptions-item label="生命周期阶段">
        <a-tag :color="phaseTagColor">
          {{ phaseLabel || '未知' }}
        </a-tag>
      </a-descriptions-item>
      <a-descriptions-item label="最近重载原因">
        {{ runtimeState?.last_reload_reason || '-' }}
      </a-descriptions-item>
      <a-descriptions-item label="最近错误">
        <span v-if="runtimeState?.last_error" class="error-text">
          {{ runtimeState.last_error }}
        </span>
        <span v-else>-</span>
      </a-descriptions-item>
      <a-descriptions-item label="重载次数">
        {{ runtimeState?.reload_count ?? '-' }}
      </a-descriptions-item>
      <a-descriptions-item label="实例版本">
        {{ runtimeState?.generation ?? '-' }}
      </a-descriptions-item>
    </a-descriptions>

    <a-result
      v-if="isFailed"
      status="error"
      title="插件异常"
      :sub-title="runtimeState?.last_error || '插件运行状态异常，请检查日志'"
      class="lifecycle-error"
    >
      <template #extra>
        <a-space>
          <a-button type="primary" @click="$emit('reload')">重载实例</a-button>
          <a-button @click="$emit('copyDiagnostics')">复制诊断信息</a-button>
        </a-space>
      </template>
    </a-result>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PluginRuntimeState } from '../types'
import {
  STATUS_LABELS,
  PHASE_LABELS,
  LIFECYCLE_STATUS_LABELS as _LIFECYCLE_STATUS_LABELS,
  LIFECYCLE_STATUS_COLORS,
  type PluginLifecycleStatus,
} from '../types'

const props = withDefaults(
  defineProps<{
    runtimeState?: PluginRuntimeState | null
    showDetails?: boolean
  }>(),
  {
    runtimeState: null,
    showDetails: true,
  }
)

defineEmits<{
  (e: 'reload'): void
  (e: 'copyDiagnostics'): void
}>()

const status = computed<PluginLifecycleStatus>(() => {
  if (!props.runtimeState) return 'discovered'
  const s = props.runtimeState.status
  const phase = props.runtimeState.lifecycle_phase

  // 生命周期状态映射：基于真实 discovery/activate/update/deactivate/failed/restart-required
  if (s === 'active') {
    if (phase === 'on_reload_prepare' || phase === 'on_reload_commit') return 'update'
    return 'active'
  }
  if (s === 'error') {
    if (phase === 'reload_failed' || phase === 'on_reload_rollback') return 'restart-required'
    return 'failed'
  }
  if (s === 'disposed' || s === 'unloaded') return 'disabled'
  if (phase === 'on_stop' || phase === 'on_unload') return 'deactivating'
  if (phase === 'on_load' || phase === 'on_start') return 'activating'
  if (s === 'loaded' || s === 'configured') return 'installed'
  return 'installed'
})

const statusLabel = computed(() => {
  if (!props.runtimeState) return '已发现'
  return STATUS_LABELS[props.runtimeState.status] || props.runtimeState.status
})

const statusColor = computed(() => LIFECYCLE_STATUS_COLORS[status.value])

const phaseLabel = computed(() => {
  if (!props.runtimeState?.lifecycle_phase) return null
  return PHASE_LABELS[props.runtimeState.lifecycle_phase] || props.runtimeState.lifecycle_phase
})

const isFailed = computed(() => status.value === 'failed')

const statusTagColor = computed(() => {
  if (!props.runtimeState) return 'default'
  const s = props.runtimeState.status
  if (s === 'active') return 'success'
  if (s === 'error') return 'error'
  if (s === 'loaded') return 'processing'
  if (s === 'disposed' || s === 'unloaded') return 'default'
  if (s === 'configured' || s === 'discovered') return 'warning'
  return 'default'
})

const phaseTagColor = computed(() => {
  if (!props.runtimeState?.lifecycle_phase) return 'default'
  const p = props.runtimeState.lifecycle_phase
  if (p === 'active') return 'green'
  if (p === 'reload_failed' || p === 'on_reload_rollback') return 'red'
  if (p === 'on_reload_prepare' || p === 'on_reload_commit') return 'cyan'
  if (p === 'on_load' || p === 'on_start') return 'blue'
  if (p === 'on_stop' || p === 'on_unload' || p === 'disposed' || p === 'unloaded') return 'default'
  return 'geekblue'
})

const phaseColor = computed(() => {
  if (phaseLabel.value) return phaseTagColor.value
  return 'default'
})
</script>

<style scoped>
/* 分隔线分组：不再以细边小卡形式嵌套（错误态 .lifecycle-error 保留强调框） */
.plugin-lifecycle-state {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
  margin-bottom: var(--v6-space-3);
  padding: var(--v6-space-3) 0 0;
  border-top: 0.5px solid var(--v6-color-border-subtle);
}

.lifecycle-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lifecycle-tag {
  font-weight: 600;
}

.lifecycle-phase-tag {
  font-size: 12px;
}

.lifecycle-details {
  margin-top: var(--v6-space-1);
}

.lifecycle-details :deep(.ant-descriptions-view) {
  background: transparent;
}

.lifecycle-details :deep(.ant-descriptions-row > th),
.lifecycle-details :deep(.ant-descriptions-row > td) {
  padding-bottom: var(--v6-space-1);
}

.lifecycle-details :deep(.ant-descriptions-item-label) {
  font-size: 12px;
  color: var(--v6-color-text-secondary);
}

.error-text {
  color: var(--v6-color-error);
  font-size: 12px;
  word-break: break-word;
}

.lifecycle-error {
  margin-top: var(--v6-space-1);
  padding: var(--v6-space-3);
  border: 0.5px solid color-mix(in srgb, var(--v6-color-error) 32%, var(--v6-color-border));
  border-radius: var(--v6-radius-card);
  background: color-mix(in srgb, var(--v6-color-error) 7%, transparent);
  text-align: left;
}

.lifecycle-error :deep(.ant-result-icon) {
  display: none;
}

.lifecycle-error :deep(.ant-result-title) {
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-semibold);
  text-align: left;
}

.lifecycle-error :deep(.ant-result-subtitle) {
  margin-top: var(--v6-space-1);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-xs);
  text-align: left;
}

.lifecycle-error :deep(.ant-result-extra) {
  margin-top: var(--v6-space-2);
  text-align: left;
}
</style>
