<script setup lang="ts">
import { computed, useId, useSlots, type Component } from 'vue'
import { DownOutlined, RightOutlined } from '@ant-design/icons-vue'

/**
 * 通用分区容器。
 *
 * 结构保留 .form-section > .section-header > h3，让 SettingsSectionLayout 的右侧目录继续
 * 自动采集锚点；支持 card（默认设置卡片）、plain（表单分区）、sub（嵌套子块）三种变体。
 */
const props = withDefaults(
  defineProps<{
    title?: string
    /** 标题下的次级说明，和标题左对齐、独占一行 */
    subtitle?: string
    icon?: Component
    variant?: 'card' | 'plain' | 'sub'
    density?: 'default' | 'compact'
    collapsible?: boolean
    anchorId?: string
  }>(),
  {
    title: undefined,
    subtitle: undefined,
    icon: undefined,
    variant: 'card',
    density: 'default',
    collapsible: false,
    anchorId: undefined,
  }
)

const collapsed = defineModel<boolean>('collapsed', { default: false })
const slots = useSlots()
const hasHeader = computed(() =>
  Boolean(props.title || props.subtitle || props.collapsible || slots.title || slots.actions)
)
const titleId = useId()
const bodyId = useId()

const toggleCollapsed = () => {
  if (!props.collapsible) return
  collapsed.value = !collapsed.value
}
</script>

<template>
  <section
    class="form-section ui-section-card"
    :class="[
      `ui-section-card--${variant}`,
      density === 'compact' ? 'ui-section-card--compact' : null,
      { 'ui-section-card--collapsed': collapsible && collapsed },
    ]"
    :data-section-anchor="anchorId"
  >
    <div v-if="hasHeader" class="section-header">
      <h3>
        <button
          v-if="collapsible"
          type="button"
          class="ui-section-card-toggle"
          :aria-expanded="!collapsed"
          :aria-controls="bodyId"
          :aria-labelledby="titleId"
          @click="toggleCollapsed"
        >
          <RightOutlined v-if="collapsed" aria-hidden="true" />
          <DownOutlined v-else aria-hidden="true" />
        </button>
        <span v-if="icon" class="ui-section-card-icon" aria-hidden="true">
          <component :is="icon" />
        </span>
        <span :id="titleId" class="ui-section-card-title">
          <slot name="title">{{ title }}</slot>
        </span>
      </h3>
      <p v-if="subtitle" class="ui-section-card-subtitle">{{ subtitle }}</p>
      <div v-if="$slots.actions" class="ui-section-card-actions">
        <slot name="actions" />
      </div>
    </div>
    <div :id="bodyId" v-show="!collapsible || !collapsed" class="ui-section-card-body">
      <slot />
    </div>
    <footer v-if="$slots.footer && (!collapsible || !collapsed)" class="ui-section-card-footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.ui-section-card {
  --section-card-padding: 24px;
  margin-bottom: 16px;
  container-type: inline-size;
}

.ui-section-card--card {
  padding: 0 var(--section-card-padding) 8px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius-lg);
  background: var(--app-appearance-surface-bg, var(--ant-color-bg-container));
}

html:not(.dark):not(.appearance-custom) .ui-section-card--card {
  border-color: var(--ant-color-border-secondary);
  box-shadow:
    0 1px 2px rgba(16, 24, 40, 0.04),
    0 4px 12px -4px rgba(16, 24, 40, 0.06);
}

.ui-section-card--plain {
  padding: 0;
  border: 0;
  background: transparent;
}

.ui-section-card--sub {
  margin-bottom: 12px;
  padding: 0;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius);
  background: transparent;
  overflow: hidden;
}

.ui-section-card--compact {
  --section-card-padding: 20px;
}

/* 头部两行网格：第一行标题 + 动作区，第二行副标题占满整行 */
.ui-section-card--card .section-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0 12px;
  margin-bottom: 0;
  min-height: 60px;
  padding: 16px 0 10px;
  border-bottom: 0;
}

.ui-section-card--card .section-header h3 {
  gap: 10px;
  min-width: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.ui-section-card--card .section-header h3::before {
  display: none;
}

.ui-section-card--plain .section-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0 12px;
  margin-bottom: 16px;
}

.ui-section-card--plain.ui-section-card--compact .section-header {
  margin-bottom: 12px;
  border-bottom-width: 1px;
}

.ui-section-card--plain.ui-section-card--compact .section-header h3 {
  gap: 10px;
  font-size: 18px;
}

.ui-section-card--plain.ui-section-card--compact .section-header h3::before {
  height: 20px;
  background: var(--ant-color-primary);
}

.ui-section-card--plain.ui-section-card--collapsed .section-header {
  margin-bottom: 0;
}

.ui-section-card--sub .section-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0 12px;
  margin-bottom: 0;
  padding: 8px 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-fill-quaternary);
}

.ui-section-card--sub.ui-section-card--collapsed .section-header {
  border-bottom: 0;
}

.ui-section-card--sub .section-header h3 {
  gap: 8px;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
}

.ui-section-card--sub .section-header h3::before {
  display: none;
}

.ui-section-card--sub .ui-section-card-body {
  padding: 12px;
}

.ui-section-card-title {
  display: inline-flex;
  align-items: center;
  gap: inherit;
  min-width: 0;
}

.ui-section-card-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: var(--ant-border-radius-sm);
  background: transparent;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.ui-section-card-toggle:hover {
  background: var(--ant-color-fill-secondary);
  color: var(--ant-color-text);
}

.ui-section-card-icon {
  display: grid;
  flex: 0 0 28px;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius-sm);
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text-secondary);
  font-size: 15px;
}

.ui-section-card-subtitle {
  grid-column: 1 / -1;
  grid-row: 2;
  margin: 6px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.ui-section-card-actions {
  display: flex;
  grid-column: 2;
  grid-row: 1;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.ui-section-card-body {
  display: flex;
  flex-direction: column;
}

.ui-section-card-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 12px var(--section-card-padding);
  border-top: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-fill-quaternary);
}

.ui-section-card--card .ui-section-card-footer {
  margin: 8px calc(-1 * var(--section-card-padding)) -8px;
  border-radius: 0 0 max(0px, calc(var(--ant-border-radius-lg) - 1px))
    max(0px, calc(var(--ant-border-radius-lg) - 1px));
}

.ui-section-card--sub .ui-section-card-footer {
  padding: 8px 12px;
}

.ui-section-card--card :deep(.ant-segmented) {
  padding: 3px;
  border: 1px solid var(--ant-color-border);
}

.ui-section-card--card
  :deep(:is(.ant-select, .ant-input, .ant-input-number, .ant-btn, .ant-segmented)) {
  font-size: 12px;
}

/* 只加强默认浅色外观的静止控件，外观包保留自身边框与选中态。 */
html:not(.dark):not(.appearance-custom)
  .ui-section-card--card
  :deep(
    :is(
        .ant-select-selector,
        .ant-input,
        .ant-input-affix-wrapper,
        .ant-input-number,
        .ant-picker,
        .ant-btn-default
      ):not(:hover):not(:focus-within)
  ) {
  border-color: var(--ant-color-text-tertiary);
}

html:not(.dark):not(.appearance-custom) .ui-section-card--card :deep(.ant-segmented-item-selected) {
  color: var(--ant-color-link);
  box-shadow: inset 0 0 0 1px var(--ant-color-text-tertiary);
}

/* 兼容现有设置页双列与关于页密度，后续随设置页统一迁至 density="compact"。 */
.settings-card-grid .ui-section-card--card,
.about-settings .ui-section-card--card {
  --section-card-padding: 20px;
}

.about-settings .ui-section-card--card .section-header {
  min-height: 0;
  padding-top: 14px;
}

.about-settings .ui-section-card--card .section-header h3 {
  font-size: 15px;
}

@container (max-width: 360px) {
  .ui-section-card-actions {
    grid-column: 1 / -1;
    grid-row: 3;
    justify-content: flex-start;
    margin-top: 8px;
  }
}
</style>
