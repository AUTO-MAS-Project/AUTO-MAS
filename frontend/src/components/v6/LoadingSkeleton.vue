<template>
  <div
    class="v6-loading-skeleton"
    :class="{
      'v6-loading-skeleton--card': card,
      'v6-loading-skeleton--inline': inline,
      'v6-loading-skeleton--animated': active && animated,
    }"
    :aria-busy="active ? 'true' : 'false'"
    :aria-label="ariaLabel"
    role="status"
    aria-live="polite"
  >
    <a-skeleton
      v-if="variant === 'default'"
      :active="active && animated"
      :paragraph="{ rows: normalizedRows, width: paragraphWidth }"
      :title="showTitle"
      :round="round"
    />
    <div v-else-if="variant === 'list'" class="v6-loading-skeleton__list">
      <div v-for="i in normalizedRows" :key="i" class="v6-loading-skeleton__list-item">
        <div class="v6-loading-skeleton__avatar" v-if="showAvatar" />
        <div class="v6-loading-skeleton__lines">
          <div class="v6-loading-skeleton__line v6-loading-skeleton__line--title" />
          <div class="v6-loading-skeleton__line v6-loading-skeleton__line--subtitle" />
        </div>
      </div>
    </div>
    <div v-else-if="variant === 'card'" class="v6-loading-skeleton__card-grid">
      <div
        v-for="i in Math.max(1, Math.min(6, normalizedRows))"
        :key="i"
        class="v6-loading-skeleton__card-item"
      >
        <div class="v6-loading-skeleton__card-image" />
        <div class="v6-loading-skeleton__card-title" />
        <div class="v6-loading-skeleton__card-desc" />
      </div>
    </div>
    <div v-else-if="variant === 'form'" class="v6-loading-skeleton__form">
      <div v-for="i in normalizedRows" :key="i" class="v6-loading-skeleton__form-row">
        <div class="v6-loading-skeleton__form-label" />
        <div class="v6-loading-skeleton__form-input" />
      </div>
    </div>
    <span v-if="active" class="v6-sr-only">{{ loadingText }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type SkeletonVariant = 'default' | 'list' | 'card' | 'form'

interface Props {
  rows?: number
  active?: boolean
  animated?: boolean
  card?: boolean
  inline?: boolean
  round?: boolean
  showTitle?: boolean
  showAvatar?: boolean
  variant?: SkeletonVariant
  ariaLabel?: string
  loadingText?: string
}

const props = withDefaults(defineProps<Props>(), {
  rows: 3,
  active: true,
  animated: true,
  card: false,
  inline: false,
  round: false,
  showTitle: true,
  showAvatar: false,
  variant: 'default',
  ariaLabel: '加载中',
  loadingText: '正在加载内容，请稍候...',
})

const normalizedRows = computed(() => Math.max(1, Math.min(12, Math.round(props.rows))))

const paragraphWidth = computed(() => {
  const widths = ['100%', '90%', '95%', '85%', '88%']
  return Array.from({ length: normalizedRows.value }, (_, i) => widths[i % widths.length])
})
</script>

<style scoped>
.v6-loading-skeleton {
  padding: var(--v6-space-4);
  background: transparent;
  border-radius: var(--v6-radius-card);
}

.v6-loading-skeleton--card {
  background: var(--v6-color-surface);
  border: 1px solid var(--v6-color-border-subtle);
  padding: var(--v6-space-6);
  box-shadow: var(--v6-shadow-card);
}

.v6-loading-skeleton--inline {
  display: inline-block;
  padding: 0;
  vertical-align: middle;
}

.v6-loading-skeleton :deep(.ant-skeleton) {
  padding: 0;
}

.v6-loading-skeleton :deep(.ant-skeleton-content .ant-skeleton-title) {
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-sm);
  height: 20px;
}

.v6-loading-skeleton :deep(.ant-skeleton-content .ant-skeleton-paragraph > li) {
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-sm);
  margin-block-start: var(--v6-space-3);
}

.v6-loading-skeleton__list-item {
  display: flex;
  gap: var(--v6-space-3);
  padding: var(--v6-space-3) 0;
}

.v6-loading-skeleton__avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--v6-color-border-subtle);
  flex-shrink: 0;
}

.v6-loading-skeleton__lines {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
  justify-content: center;
}

.v6-loading-skeleton__line {
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-sm);
  height: 14px;
}

.v6-loading-skeleton__line--title {
  width: 45%;
  height: 16px;
}

.v6-loading-skeleton__line--subtitle {
  width: 75%;
}

.v6-loading-skeleton__card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--v6-space-4);
}

.v6-loading-skeleton__card-item {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-3);
}

.v6-loading-skeleton__card-image {
  width: 100%;
  aspect-ratio: 16 / 10;
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-md);
}

.v6-loading-skeleton__card-title {
  height: 16px;
  width: 60%;
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-sm);
}

.v6-loading-skeleton__card-desc {
  height: 12px;
  width: 85%;
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-sm);
}

.v6-loading-skeleton__form {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-4);
}

.v6-loading-skeleton__form-row {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
}

.v6-loading-skeleton__form-label {
  height: 14px;
  width: 25%;
  min-width: 80px;
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-sm);
}

.v6-loading-skeleton__form-input {
  height: 36px;
  width: 100%;
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-control);
}

.v6-loading-skeleton--animated :deep(.ant-skeleton-content .ant-skeleton-title),
.v6-loading-skeleton--animated :deep(.ant-skeleton-content .ant-skeleton-paragraph > li),
.v6-loading-skeleton--animated .v6-loading-skeleton__avatar,
.v6-loading-skeleton--animated .v6-loading-skeleton__line,
.v6-loading-skeleton--animated .v6-loading-skeleton__card-image,
.v6-loading-skeleton--animated .v6-loading-skeleton__card-title,
.v6-loading-skeleton--animated .v6-loading-skeleton__card-desc,
.v6-loading-skeleton--animated .v6-loading-skeleton__form-label,
.v6-loading-skeleton--animated .v6-loading-skeleton__form-input {
  background: linear-gradient(
    90deg,
    var(--v6-color-border-subtle) 25%,
    var(--v6-color-border) 50%,
    var(--v6-color-border-subtle) 75%
  );
  background-size: 200% 100%;
  animation: v6-skeleton-shimmer 1.5s ease-in-out infinite;
}

@keyframes v6-skeleton-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

:root[data-perf-mode='low']
  .v6-loading-skeleton--animated
  :deep(.ant-skeleton-content .ant-skeleton-title),
:root[data-perf-mode='low']
  .v6-loading-skeleton--animated
  :deep(.ant-skeleton-content .ant-skeleton-paragraph > li),
:root[data-perf-mode='low'] .v6-loading-skeleton--animated .v6-loading-skeleton__avatar,
:root[data-perf-mode='low'] .v6-loading-skeleton--animated .v6-loading-skeleton__line,
:root[data-perf-mode='low'] .v6-loading-skeleton--animated .v6-loading-skeleton__card-image,
:root[data-perf-mode='low'] .v6-loading-skeleton--animated .v6-loading-skeleton__card-title,
:root[data-perf-mode='low'] .v6-loading-skeleton--animated .v6-loading-skeleton__card-desc,
:root[data-perf-mode='low'] .v6-loading-skeleton--animated .v6-loading-skeleton__form-label,
:root[data-perf-mode='low'] .v6-loading-skeleton--animated .v6-loading-skeleton__form-input {
  animation: none;
  background: var(--v6-color-border-subtle);
}

@media (prefers-reduced-motion: reduce) {
  .v6-loading-skeleton--animated :deep(.ant-skeleton-content .ant-skeleton-title),
  .v6-loading-skeleton--animated :deep(.ant-skeleton-content .ant-skeleton-paragraph > li),
  .v6-loading-skeleton--animated .v6-loading-skeleton__avatar,
  .v6-loading-skeleton--animated .v6-loading-skeleton__line,
  .v6-loading-skeleton--animated .v6-loading-skeleton__card-image,
  .v6-loading-skeleton--animated .v6-loading-skeleton__card-title,
  .v6-loading-skeleton--animated .v6-loading-skeleton__card-desc,
  .v6-loading-skeleton--animated .v6-loading-skeleton__form-label,
  .v6-loading-skeleton--animated .v6-loading-skeleton__form-input {
    animation: none;
  }
}

.v6-loading-skeleton :deep(.ant-skeleton-content) {
  pointer-events: none;
}
</style>
