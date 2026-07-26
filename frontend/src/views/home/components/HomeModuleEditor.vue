<template>
  <div class="module-editor-bar">
    <div class="module-editor-title">{{ title }}</div>
    <div class="module-editor-options">
      <label class="module-editor-option">
        <span>展示</span>
        <a-switch
          size="small"
          :checked="isShown"
          :aria-label="`${title} 展示开关`"
          @change="$emit('toggle-shown', $event)"
        />
      </label>
    </div>
    <div class="module-editor-actions">
      <a-tooltip title="上移">
        <a-button
          type="text"
          size="small"
          :disabled="!canMoveUp"
          :aria-label="`上移 ${title}`"
          @click="$emit('move', 'up')"
        >
          <template #icon>
            <ArrowUpOutlined />
          </template>
        </a-button>
      </a-tooltip>
      <a-tooltip title="下移">
        <a-button
          type="text"
          size="small"
          :disabled="!canMoveDown"
          :aria-label="`下移 ${title}`"
          @click="$emit('move', 'down')"
        >
          <template #icon>
            <ArrowDownOutlined />
          </template>
        </a-button>
      </a-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons-vue'

interface Props {
  title: string
  isShown: boolean
  canMoveUp: boolean
  canMoveDown: boolean
}

defineProps<Props>()

defineEmits<{
  (e: 'toggle-shown', checked: boolean | string | number): void
  (e: 'move', direction: 'up' | 'down'): void
}>()
</script>

<style scoped>
.module-editor-bar {
  min-height: 40px;
  padding: 7px 10px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-md);
  background: var(--v6-color-surface);
}

.module-editor-title {
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--v6-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.module-editor-options {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.module-editor-option {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--v6-color-text-secondary);
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}

.module-editor-actions {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.module-editor-options + .module-editor-actions {
  margin-left: 0;
}
</style>
