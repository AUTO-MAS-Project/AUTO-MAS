<template>
  <div class="v6-empty-state" role="status" aria-live="polite">
    <a-empty :description="false">
      <template #image>
        <component :is="resolvedIcon" class="v6-empty-state__icon" aria-hidden="true" />
      </template>
      <template #description>
        <div class="v6-empty-state__body">
          <p v-if="title" class="v6-empty-state__title">{{ title }}</p>
          <p v-if="description" class="v6-empty-state__description">{{ description }}</p>
          <slot name="actions" />
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
}

const props = withDefaults(defineProps<Props>(), {
  title: '暂无数据',
  description: '',
  icon: undefined,
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

.v6-empty-state__icon {
  font-size: 40px;
  color: var(--v6-color-text-tertiary);
  margin-bottom: var(--v6-space-4);
}

.v6-empty-state__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--v6-space-1);
  text-align: center;
  max-width: 360px;
}

.v6-empty-state__title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: var(--v6-color-text);
}

.v6-empty-state__description {
  margin: 0;
  font-size: 13px;
  color: var(--v6-color-text-secondary);
  line-height: 1.5;
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
</style>
