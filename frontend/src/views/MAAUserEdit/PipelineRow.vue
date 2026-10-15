<template>
  <div class="task-row" :class="{ 'is-off': !checked, 'is-expanded': expanded }">
    <div class="row-head">
      <!-- 一级任务用 switch（44x22），二级子项用 16px 勾选框：2.75 倍尺寸差建立层级，
           同时符合 HIG「立即生效的设置用 switch、组内选项用 checkbox」。
           任务名在同级的展开按钮内，无法用 <label> 包裹，故用 aria-label 给读屏同一串文字 -->
      <span class="toggle-slot">
        <a-switch
          v-if="toggleable"
          :checked="checked"
          :disabled="disabled"
          :aria-label="name"
          @change="emit('change', $event as boolean)"
        />
      </span>
      <component
        :is="hasDetail ? 'button' : 'div'"
        :type="hasDetail ? 'button' : undefined"
        class="row-main"
        :class="{ 'row-main-static': !hasDetail }"
        :aria-expanded="hasDetail ? expanded : undefined"
        @click="hasDetail && (expanded = !expanded)"
      >
        <span v-if="step !== undefined" class="row-step" aria-hidden="true">{{ step }}</span>
        <span class="row-name">{{ name }}</span>
        <span class="row-summary" :class="{ 'row-summary-rich': $slots.summary }">
          <slot name="summary">{{ summary }}</slot>
        </span>
      </component>
      <div v-if="hasDetail || $slots.actions || hint" class="row-actions">
        <!-- 长说明收进可聚焦的 ? ：键盘与触屏能拿到，同时不再和正文抢注意力 -->
        <a-tooltip v-if="hint" :title="hint" :trigger="['hover', 'focus']">
          <button type="button" class="row-help" :aria-label="hint">
            <QuestionCircleOutlined />
          </button>
        </a-tooltip>
        <slot name="actions" />
        <button
          v-if="hasDetail"
          type="button"
          class="row-main row-expand"
          :aria-label="name"
          :aria-expanded="expanded"
          @click="expanded = !expanded"
        >
          <DownOutlined class="row-chevron" />
        </button>
      </div>
    </div>
    <div v-if="hasDetail && expanded" class="row-detail">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { DownOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'

withDefaults(
  defineProps<{
    name: string
    /** 流水线阶段序号；不传则不占位（任务清单里的行没有先后关系） */
    step?: number
    summary?: string
    checked: boolean
    disabled?: boolean
    hasDetail?: boolean
    hint?: string
    toggleable?: boolean
  }>(),
  { step: undefined, summary: '', disabled: false, hasDetail: true, hint: '', toggleable: true }
)

const emit = defineEmits<{ change: [checked: boolean] }>()

const expanded = ref(false)
</script>

<style scoped>
.task-row {
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.task-row:last-child {
  border-bottom: none;
}

.row-head {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 52px;
  padding: 6px 4px;
}

.row-main {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
  min-height: 40px;
  padding: 0 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s ease;
}

.row-main-static {
  cursor: default;
}

.row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  /* 行尾只保留一个展开箭头，固定在右边缘；齿轮/说明图标排在它左边。 */
  min-width: 68px;
  flex-shrink: 0;
}

.row-expand {
  flex: 0 0 32px;
  justify-content: center;
  min-height: 32px;
  padding: 0;
}

.row-main:not(.row-main-static):hover {
  background: var(--ant-color-fill-quaternary);
}

.row-main:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 1px;
}

/* 固定槽位宽度，无开关的行（日常任务）也留位，保持任务名列对齐 */
.toggle-slot {
  flex: 0 0 44px;
  display: flex;
  align-items: center;
}

.row-step {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--ant-color-fill-secondary);
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.row-help {
  flex: 0 0 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
}

.row-help:hover {
  color: var(--ant-color-primary);
}

.row-help:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 1px;
}

.row-name {
  flex: 0 0 auto;
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
}

/* 关闭态用 text-secondary 而非 text-tertiary：15px/600 不算 WCAG 大字，
   tertiary 在浅色模式下仅 3.36:1 不达 AA，secondary 为 7.00:1 且照样压暗 */
.is-off .row-name {
  color: var(--ant-color-text-secondary);
}

.row-summary {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

/* 摘要位放控件（如日常任务勾选框）时不能截断 */
.row-summary-rich {
  overflow: visible;
  white-space: normal;
}

.row-chevron {
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  transition: transform 0.2s ease;
}

.is-expanded .row-chevron {
  transform: rotate(180deg);
}

/* 左内边距对齐任务名列（4 行内边距 + 44 开关槽 + 12 间隙 + 8 row-main 内边距），
   表明「这些配置属于上面那个任务」 */
.row-detail {
  padding: 4px 8px 16px 68px;
}

@media (max-width: 768px) {
  .row-main {
    flex-wrap: wrap;
    gap: 4px 12px;
  }

  .row-summary {
    flex: 1 0 100%;
  }

  .row-detail {
    padding-left: 8px;
  }
}
</style>
