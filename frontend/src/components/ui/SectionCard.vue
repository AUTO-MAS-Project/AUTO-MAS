<script setup lang="ts">
import type { Component } from 'vue'

/**
 * 设置类页面的分区卡片。
 *
 * 结构刻意保留 .form-section > .section-header > h3（h3 必须是 .section-header 的直接子元素），
 * 让 SettingsSectionLayout 的右侧目录继续自动采集锚点；视觉上把通栏分隔线换成卡片边框，
 * 卡片内由 SettingRow 的行分隔线承担分组。
 */
defineProps<{
  title?: string
  /** 标题下的次级说明，和标题左对齐、独占一行 */
  subtitle?: string
  icon?: Component
}>()
</script>

<template>
  <section class="form-section ui-section-card">
    <div class="section-header">
      <h3>
        <span v-if="icon" class="ui-section-card-icon" aria-hidden="true">
          <component :is="icon" />
        </span>
        <slot name="title">{{ title }}</slot>
      </h3>
      <p v-if="subtitle" class="ui-section-card-subtitle">{{ subtitle }}</p>
      <div v-if="$slots.actions" class="ui-section-card-actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="ui-section-card-body">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="ui-section-card-footer">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.ui-section-card {
  --section-card-padding: 24px;
  margin-bottom: 16px;
  padding: 0 var(--section-card-padding) 8px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius-lg);
  background: var(--app-appearance-surface-bg, var(--ant-color-bg-container));
  container-type: inline-size;
}

html:not(.dark):not(.appearance-custom) .ui-section-card {
  /* 卡片已回到纯白，边框不再需要压到 #cacaca 去冒充分隔；
     与发丝线保持同一档，深度交给下面的极轻阴影。 */
  border-color: var(--ant-color-border-secondary);
  box-shadow:
    0 1px 2px rgba(16, 24, 40, 0.04),
    0 4px 12px -4px rgba(16, 24, 40, 0.06);
}

/* 头部两行网格：第一行标题 + 动作区，第二行副标题占满整行 */
.ui-section-card .section-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0 12px;
  margin-bottom: 0;
  min-height: 60px;
  padding: 16px 0 10px;
  border-bottom: 0;
}

.ui-section-card .section-header h3 {
  gap: 10px;
  min-width: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.ui-section-card .section-header h3::before {
  display: none;
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
  margin: 8px calc(-1 * var(--section-card-padding)) -8px;
  padding: 12px var(--section-card-padding);
  border-top: 1px solid var(--ant-color-border-secondary);
  border-radius: 0 0 max(0px, calc(var(--ant-border-radius-lg) - 1px))
    max(0px, calc(var(--ant-border-radius-lg) - 1px));
  background: var(--ant-color-fill-quaternary);
}

.ui-section-card :deep(.ant-segmented) {
  padding: 3px;
  border: 1px solid var(--ant-color-border);
}

.ui-section-card :deep(:is(.ant-select, .ant-input, .ant-input-number, .ant-btn, .ant-segmented)) {
  font-size: 12px;
}

/* 只加强默认浅色外观的静止控件，外观包保留自身边框与选中态。 */
html:not(.dark):not(.appearance-custom)
  .ui-section-card
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

html:not(.dark):not(.appearance-custom) .ui-section-card :deep(.ant-segmented-item-selected) {
  color: var(--ant-color-link);
  box-shadow: inset 0 0 0 1px var(--ant-color-text-tertiary);
}

.settings-card-grid .ui-section-card,
.about-settings .ui-section-card {
  --section-card-padding: 20px;
}

/* 关于页保持原先的卡片密度。 */
.about-settings .ui-section-card .section-header {
  min-height: 0;
  padding-top: 14px;
}

.about-settings .ui-section-card .section-header h3 {
  font-size: 15px;
}

@container (max-width: 480px) {
  .ui-section-card-actions {
    grid-column: 1 / -1;
    grid-row: 3;
    justify-content: flex-start;
    margin-top: 8px;
  }
}
</style>
