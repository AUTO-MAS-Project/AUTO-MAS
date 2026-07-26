<template>
  <div
    class="v6-empty-state"
    :class="{ 'v6-empty-state--compact': compact }"
    role="status"
    aria-live="polite"
  >
    <a-empty :description="false">
      <template #image>
        <div class="v6-empty-state__icon-wrapper">
          <slot name="icon">
            <component :is="resolvedIcon" class="v6-empty-state__icon" aria-hidden="true" />
          </slot>
        </div>
      </template>
      <template #description>
        <div class="v6-empty-state__body">
          <p v-if="title" class="v6-empty-state__title">{{ title }}</p>
          <p v-if="description" class="v6-empty-state__description">{{ description }}</p>
          <div v-if="$slots.actions || $slots.action" class="v6-empty-state__actions">
            <slot name="actions" />
            <slot name="action" />
          </div>
        </div>
      </template>
    </a-empty>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import { InboxOutlined } from '@ant-design/icons-vue'

interface Props {
  title?: string
  description?: string
  icon?: Component
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '暂无数据',
  description: '',
  icon: undefined,
  compact: false,
})

const resolvedIcon = computed<Component>(() => props.icon ?? InboxOutlined)
</script>

<style scoped>
.v6-empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--v6-space-8) var(--v6-space-6);
  color: var(--v6-color-text-secondary);
}

.v6-empty-state--compact {
  padding: var(--v6-space-4) var(--v6-space-3);
}

.v6-empty-state__icon-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
}

.v6-empty-state__icon {
  font-size: 40px;
  color: var(--v6-color-text-tertiary);
  margin-bottom: var(--v6-space-4);
  transition: font-size 0.2s ease;
}

.v6-empty-state--compact .v6-empty-state__icon {
  font-size: 28px;
  margin-bottom: var(--v6-space-2);
}

.v6-empty-state__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--v6-space-1);
  text-align: center;
  max-width: 360px;
}

.v6-empty-state--compact .v6-empty-state__body {
  gap: 2px;
}

.v6-empty-state__title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--v6-color-text);
  transition: font-size 0.2s ease;
}

.v6-empty-state--compact .v6-empty-state__title {
  font-size: 13px;
}

.v6-empty-state__description {
  margin: 0;
  font-size: 13px;
  color: var(--v6-color-text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  transition: font-size 0.2s ease;
}

.v6-empty-state--compact .v6-empty-state__description {
  font-size: 12px;
  line-height: 1.5;
}

.v6-empty-state__actions {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  margin-top: var(--v6-space-3);
  flex-wrap: wrap;
  justify-content: center;
}

.v6-empty-state--compact .v6-empty-state__actions {
  margin-top: var(--v6-space-2);
  gap: var(--v6-space-1);
}

/* 隐藏 a-empty 默认 image 容器内的占位字符串展示，仅用图标 */
.v6-empty-state :deep(.ant-empty-image) {
  height: auto;
  margin-bottom: 0;
}

/* antd 把 #description 插槽包在 .ant-empty-description 内，重置默认样式 */
.v6-empty-state :deep(.ant-empty-description) {
  margin: 0;
  color: inherit;
}

/* 低性能模式 / reduced-motion 下去除过渡 */
:root[data-perf-mode='low'] .v6-empty-state__icon,
:root[data-perf-mode='low'] .v6-empty-state__title,
:root[data-perf-mode='low'] .v6-empty-state__description {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .v6-empty-state__icon,
  .v6-empty-state__title,
  .v6-empty-state__description {
    transition: none;
  }
}
</style>
