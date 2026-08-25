<template>
  <a-tooltip v-if="hint" :title="hint">
    <span class="form-label">
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
.form-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 13px;
  color: var(--ant-color-text);
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
