<script setup lang="ts">
/**
 * 状态胶囊：把「有效 · 剩余 165 天」「已暂停至 …」这类状态文字从灰字正文里提出来，
 * 正常/警示一眼可分。只做展示，不承担交互。
 */
withDefaults(
  defineProps<{
    tone?: 'success' | 'warning' | 'error' | 'neutral'
    /** 前置圆点，正常状态用它，纯文字标签可以关掉 */
    dot?: boolean
  }>(),
  { tone: 'neutral', dot: true }
)
</script>

<template>
  <span class="ui-chip" :class="`ui-chip--${tone}`">
    <span v-if="dot" class="ui-chip-dot" aria-hidden="true" />
    <slot />
  </span>
</template>

<style scoped>
.ui-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 2px 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
}

.ui-chip-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  border-radius: 50%;
  background: currentcolor;
}

.ui-chip--success {
  border-color: var(--ant-color-success-border);
  color: var(--ant-color-success);
  background: var(--ant-color-success-bg);
}

.ui-chip--warning {
  border-color: var(--ant-color-warning-border);
  color: var(--ant-color-warning-text);
  background: var(--ant-color-warning-bg);
}

.ui-chip--error {
  border-color: var(--ant-color-error-border);
  color: var(--ant-color-error);
  background: var(--ant-color-error-bg);
}

.ui-chip--neutral {
  border-color: var(--ant-color-border-secondary);
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-secondary);
}
</style>
