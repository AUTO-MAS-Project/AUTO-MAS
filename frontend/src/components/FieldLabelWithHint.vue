<template>
  <!-- focus 也能触发：只挂 hover 的话键盘用户拿不到提示（WCAG 1.4.13） -->
  <a-tooltip v-if="hint" :title="hint" :trigger="['hover', 'focus']">
    <span class="field-label" tabindex="0">
      {{ text }}
      <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
    </span>
  </a-tooltip>
  <span v-else class="field-label">{{ text }}</span>
</template>

<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

defineProps<{
  text: string
  hint?: string
}>()
</script>

<style scoped>
/* 二级配置标签：与任务名（15px/600/primary）拉开层级，体现从属关系 */
.field-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-weight: 500;
}

.field-label:focus-visible {
  border-radius: 3px;
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
  cursor: help;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}
</style>
