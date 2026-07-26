<template>
  <div class="setting-tab-header">
    <div v-if="description" class="setting-tab-summary">{{ description }}</div>

    <div class="setting-tab-actions">
      <a-button
        v-if="canRestoreDefaults"
        size="small"
        :disabled="restoring"
        @click="$emit('restore-defaults')"
      >
        <template #icon><UndoOutlined /></template>
        恢复默认
      </a-button>
      <a-button
        v-if="hasPending"
        size="small"
        type="primary"
        :loading="retrying"
        @click="$emit('retry-pending')"
      >
        重试保存
      </a-button>
      <slot name="extra-actions" />
    </div>

    <div v-if="error || hasPending" class="setting-tab-alerts">
      <a-alert
        v-if="error"
        type="error"
        :message="error"
        show-icon
        closable
        @close="$emit('clear-error')"
      >
        <template #action>
          <a-button size="small" danger @click="$emit('retry-pending')">重试</a-button>
        </template>
      </a-alert>

      <a-alert
        v-if="hasPending"
        type="warning"
        :message="`有 ${pendingCount} 项修改未保存到后端。`"
        show-icon
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { UndoOutlined } from '@ant-design/icons-vue'

defineProps<{
  description?: string
  error?: string | null
  hasPending?: boolean
  pendingCount?: number
  retrying?: boolean
  restoring?: boolean
  canRestoreDefaults?: boolean
}>()

defineEmits<{
  'restore-defaults': []
  'retry-pending': []
  'clear-error': []
}>()
</script>

<style scoped>
.setting-tab-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--v6-space-2);
  margin-bottom: var(--v6-space-3);
  padding: var(--v6-space-1) 0;
}

.setting-tab-summary {
  flex: 1;
  min-width: 0;
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  line-height: var(--v6-line-height-normal);
}

.setting-tab-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: var(--v6-space-2);
}

.setting-tab-alerts {
  flex-basis: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
}

@container settings-content (max-width: 640px) {
  .setting-tab-summary {
    flex-basis: 100%;
  }

  .setting-tab-actions {
    align-self: flex-end;
  }
}
</style>
