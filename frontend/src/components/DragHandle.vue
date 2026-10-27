<template>
  <span class="drag-handle" :title="title" :aria-label="ariaLabel ?? title">
    <HolderOutlined aria-hidden="true" />
  </span>
</template>

<script setup lang="ts">
import { HolderOutlined } from '@ant-design/icons-vue'

interface Props {
  title: string
  ariaLabel?: string
}

defineProps<Props>()
</script>

<style scoped>
.drag-handle {
  width: 16px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  cursor: grab;
  user-select: none;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-handle :deep(.anticon) {
  font-size: 14px;
}
</style>
