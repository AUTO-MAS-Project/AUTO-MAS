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
  margin-bottom: 16px;
  padding: 0 20px 8px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--app-appearance-surface-bg, var(--ant-color-bg-container));
  container-type: inline-size;
}

/* 头部两行网格：第一行标题 + 动作区，第二行副标题占满整行 */
.ui-section-card .section-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0 12px;
  margin-bottom: 0;
  padding: 14px 0 10px;
  border-bottom: 0;
}

.ui-section-card .section-header h3 {
  gap: 10px;
  min-width: 0;
  font-size: 15px;
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
  border-radius: 7px;
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
  margin: 8px -20px -8px;
  padding: 12px 20px;
  border-top: 1px solid var(--ant-color-border-secondary);
  border-radius: 0 0 10px 10px;
  background: var(--ant-color-fill-quaternary);
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
