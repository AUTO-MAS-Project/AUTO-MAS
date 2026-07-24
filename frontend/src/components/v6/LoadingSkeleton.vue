<template>
  <div
    class="v6-loading-skeleton"
    :aria-busy="active ? 'true' : 'false'"
    role="status"
    aria-live="polite"
  >
    <a-skeleton :active="active" :paragraph="{ rows: normalizedRows }" :title="true" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  rows?: number
  active?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  rows: 3,
  active: true,
})

const normalizedRows = computed(() => Math.max(1, Math.min(12, Math.round(props.rows))))
</script>

<style scoped>
.v6-loading-skeleton {
  padding: var(--v6-space-4) var(--v6-space-6);
  background: var(--v6-color-surface);
  border-radius: var(--v6-radius-card);
}

.v6-loading-skeleton :deep(.ant-skeleton-content .ant-skeleton-title) {
  background: var(--v6-color-border-subtle);
}

.v6-loading-skeleton :deep(.ant-skeleton-content .ant-skeleton-paragraph > li) {
  background: var(--v6-color-border-subtle);
}

/* 屏幕阅读器：仅宣告状态，避免朗读骨架占位符 */
.v6-loading-skeleton :deep(.ant-skeleton-content) {
  pointer-events: none;
}
</style>
