<template>
  <PageHeader
    class="script-edit-page-header"
    :title="title"
    :subtitle="subtitle"
    :bordered="false"
    compact
    transparent
  >
    <template #title>
      <div class="script-edit-page-header__title">
        <img
          v-if="icon"
          :src="icon"
          :alt="iconAlt || ''"
          class="script-edit-page-header__icon"
          @error="emit('icon-error', $event)"
        />
        <span>{{ title }}</span>
        <a-tag v-if="typeLabel" :color="typeColor" class="script-edit-page-header__type">
          {{ typeLabel }}
        </a-tag>
        <slot name="status" />
      </div>
    </template>

    <slot name="meta" />

    <template #actions>
      <slot name="actions" />
      <a-button class="script-edit-page-header__back" @click="emit('back')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </template>
  </PageHeader>
</template>

<script setup lang="ts">
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/mac/PageHeader.vue'

interface Props {
  title: string
  subtitle?: string
  icon?: string
  iconAlt?: string
  typeLabel?: string
  typeColor?: string
}

withDefaults(defineProps<Props>(), {
  subtitle: '配置脚本运行方式与专项能力',
  icon: undefined,
  iconAlt: undefined,
  typeLabel: undefined,
  typeColor: undefined,
})

const emit = defineEmits<{
  back: []
  'icon-error': [event: Event]
}>()
</script>

<style scoped>
.script-edit-page-header {
  min-width: 0;
}

.script-edit-page-header__title {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: var(--v6-space-2);
}

.script-edit-page-header__title > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.script-edit-page-header__icon {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  border-radius: var(--v6-radius-sm);
  object-fit: contain;
}

.script-edit-page-header__type {
  flex: none;
  margin-inline-end: 0;
  border-radius: var(--v6-radius-pill);
}

.script-edit-page-header__back {
  border-radius: var(--v6-radius-control);
}

@media (max-width: 1100px) {
  .script-edit-page-header {
    width: 100%;
  }
}

@media (max-width: 720px) {
  .script-edit-page-header :deep(.mac-page-header) {
    align-items: stretch;
    flex-direction: column;
  }

  .script-edit-page-header :deep(.mac-page-header__actions) {
    width: 100%;
    flex-wrap: wrap;
  }

  .script-edit-page-header__type {
    display: none;
  }
}
</style>
