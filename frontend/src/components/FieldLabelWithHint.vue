<template>
  <span class="field-label" :class="{ 'field-label-form': variant === 'form' }">
    {{ text }}
    <!-- 只以问号定位；保留 focus，让键盘用户也能读取提示。 -->
    <a-tooltip v-if="hint" :title="hint" :trigger="['hover', 'focus']">
      <QuestionCircleOutlined class="help-icon" tabindex="0" :aria-label="hint" />
    </a-tooltip>
  </span>
</template>

<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

defineProps<{
  text: string
  hint?: string
  variant?: 'secondary' | 'form'
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

.help-icon:focus-visible {
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

/* 主表单标签保留现有层级，二级配置仍使用默认样式。 */
.field-label-form {
  gap: 8px;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.field-label-form .help-icon {
  font-size: 14px;
  transition: color 0.3s ease;
}
</style>
