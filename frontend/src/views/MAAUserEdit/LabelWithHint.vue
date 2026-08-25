<template>
  <!-- focus 也能触发：只挂 hover 的话键盘用户拿不到提示（WCAG 1.4.13） -->
  <a-tooltip v-if="hint" :title="hint" :trigger="['hover', 'focus']">
    <span class="form-label" tabindex="0">
      {{ text }}
      <QuestionCircleOutlined class="help-icon" />
    </span>
  </a-tooltip>
  <span v-else class="form-label">{{ text }}</span>
</template>

<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

defineProps<{ text: string; hint?: string }>()
</script>

<style scoped>
/* 二级配置标签：与流水线任务名（15px/600/primary）拉开三级差，体现从属关系 */
.form-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.form-label:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
  border-radius: 3px;
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
