<template>
  <a-drawer
    :open="open"
    :title="t('home.layout.title')"
    :width="360"
    :mask="false"
    :root-style="drawerRootStyle"
    placement="right"
    @close="emit('update:open', false)"
  >
    <draggable
      :model-value="modules"
      item-key="key"
      :animation="180"
      handle=".home-layout-drag-handle"
      ghost-class="home-layout-ghost"
      chosen-class="home-layout-chosen"
      class="home-layout-list"
      @update:model-value="onReorder"
    >
      <template #item="{ element: module }">
        <div class="home-layout-item">
          <span
            class="home-layout-drag-handle"
            role="button"
            tabindex="0"
            :aria-label="t('home.layout.drag')"
            :title="t('home.layout.drag')"
          >
            <MenuOutlined />
          </span>
          <span class="home-layout-title">{{ module.title }}</span>
          <a-switch
            size="small"
            :checked="module.visible"
            :aria-label="t('home.layout.visibility', { name: module.title })"
            @change="onVisibilityChange(module.key, $event)"
          />
        </div>
      </template>
    </draggable>

    <a-divider style="margin: 16px 0" />

    <div class="home-layout-extra">
      <span class="home-layout-title">{{ t('home.layout.scrollHint') }}</span>
      <a-switch
        size="small"
        :checked="!scrollHintHidden"
        :aria-label="t('home.layout.scrollHintVisibility')"
        @change="emit('scroll-hint-change', !$event)"
      />
    </div>
  </a-drawer>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { CSSProperties } from 'vue'
import { MenuOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import type { HomeModuleDescriptor, HomeModuleKey } from '@/types/home'

defineOptions({
  name: 'HomeLayoutDrawer',
})

interface Props {
  open: boolean
  modules: HomeModuleDescriptor[]
  scrollHintHidden: boolean
}

const { t } = useI18n()

defineProps<Props>()

const drawerRootStyle: CSSProperties = {
  top: '32px',
  height: 'calc(100% - 32px)',
}

const emit = defineEmits<{
  'update:open': [value: boolean]
  reorder: [order: HomeModuleKey[]]
  'visibility-change': [key: HomeModuleKey, visible: boolean]
  'scroll-hint-change': [hidden: boolean]
}>()

const onReorder = (modules: HomeModuleDescriptor[]) => {
  emit(
    'reorder',
    modules.map(module => module.key)
  )
}

const onVisibilityChange = (key: HomeModuleKey, value: boolean | string | number) => {
  emit('visibility-change', key, Boolean(value))
}
</script>

<style scoped>
.home-layout-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.home-layout-item {
  min-height: 48px;
  padding: 8px 12px;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  color: var(--ant-color-text);
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.home-layout-drag-handle {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  border-radius: 6px;
  cursor: grab;
  user-select: none;
}

.home-layout-drag-handle:hover,
.home-layout-drag-handle:focus-visible {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  outline: none;
}

.home-layout-drag-handle:active,
.home-layout-chosen .home-layout-drag-handle {
  cursor: grabbing;
}

.home-layout-title {
  min-width: 0;
  overflow: hidden;
  font-size: 14px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.home-layout-ghost {
  opacity: 0.35;
}

.home-layout-extra {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}
</style>
