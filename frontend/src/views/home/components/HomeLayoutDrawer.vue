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
        <div class="home-layout-entry">
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

          <!-- 轮播是一组游戏卡的容器：上面的开关是总闸，这里逐个游戏单独控制 -->
          <div
            v-if="module.key === HOME_ACTIVITY_CAROUSEL_KEY"
            class="home-layout-children"
            :class="{ 'is-muted': !module.visible }"
          >
            <div class="home-layout-children-hint">{{ t('home.layout.activityGroup') }}</div>

            <draggable
              :model-value="activityModules"
              item-key="key"
              :animation="180"
              handle=".home-layout-sub-drag-handle"
              ghost-class="home-layout-ghost"
              chosen-class="home-layout-chosen"
              class="home-layout-list"
              @update:model-value="onActivityReorder"
            >
              <template #item="{ element: game }">
                <div class="home-layout-item is-sub">
                  <span
                    class="home-layout-sub-drag-handle"
                    role="button"
                    tabindex="0"
                    :aria-label="t('home.layout.drag')"
                    :title="t('home.layout.drag')"
                  >
                    <MenuOutlined />
                  </span>
                  <span class="home-layout-title">{{ game.title }}</span>
                  <a-switch
                    size="small"
                    :checked="game.visible"
                    :aria-label="t('home.layout.visibility', { name: game.title })"
                    @change="onVisibilityChange(game.key, $event)"
                  />
                </div>
              </template>
            </draggable>

            <div class="home-layout-extra is-sub">
              <span class="home-layout-title">{{ t('home.layout.carouselAutoplay') }}</span>
              <a-switch
                size="small"
                :checked="carouselAutoplay"
                :aria-label="t('home.layout.carouselAutoplayVisibility')"
                @change="emit('autoplay-change', Boolean($event))"
              />
            </div>
          </div>
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
import { HOME_ACTIVITY_CAROUSEL_KEY } from '@/views/home/homeLayoutConfig'

defineOptions({
  name: 'HomeLayoutDrawer',
})

interface Props {
  open: boolean
  modules: HomeModuleDescriptor[]
  activityModules: HomeModuleDescriptor[]
  scrollHintHidden: boolean
  carouselAutoplay: boolean
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
  'reorder-activities': [order: HomeModuleKey[]]
  'visibility-change': [key: HomeModuleKey, visible: boolean]
  'scroll-hint-change': [hidden: boolean]
  'autoplay-change': [autoplay: boolean]
}>()

const toKeys = (modules: HomeModuleDescriptor[]) => modules.map(module => module.key)

const onReorder = (modules: HomeModuleDescriptor[]) => {
  emit('reorder', toKeys(modules))
}

const onActivityReorder = (modules: HomeModuleDescriptor[]) => {
  emit('reorder-activities', toKeys(modules))
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

.home-layout-entry {
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

.home-layout-item.is-sub {
  min-height: 40px;
  padding: 4px 10px;
  background: var(--ant-color-bg-container);
}

.home-layout-children {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-left: 20px;
  padding: 10px 10px 10px 12px;
  background: var(--ant-color-fill-quaternary);
  border-left: 2px solid var(--ant-color-border-secondary);
  border-radius: 0 8px 8px 0;
  transition: opacity 0.2s ease;
}

/* 总闸关掉后子项仍可预先配置，只是弱化提示它们当前不生效 */
.home-layout-children.is-muted {
  opacity: 0.5;
}

.home-layout-children-hint {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

/* 两级列表的手柄类名必须互斥：外层 draggable 的 handle 选择器只认外层那个，
   否则内层手柄也会命中外层，能不能拖对全看 Sortable 的全局守卫 */
.home-layout-drag-handle,
.home-layout-sub-drag-handle {
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
.home-layout-drag-handle:focus-visible,
.home-layout-sub-drag-handle:hover,
.home-layout-sub-drag-handle:focus-visible {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  outline: none;
}

.home-layout-drag-handle:active,
.home-layout-sub-drag-handle:active,
.home-layout-chosen .home-layout-drag-handle,
.home-layout-chosen .home-layout-sub-drag-handle {
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
  color: var(--ant-color-text);
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.home-layout-extra.is-sub {
  padding: 4px 10px;
  background: var(--ant-color-bg-container);
}
</style>
