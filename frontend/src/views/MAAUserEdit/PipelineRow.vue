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
        <span class="row-name">{{ name }}</span>
        <span class="row-summary" :class="{ 'row-summary-rich': $slots.summary }">
          <slot name="summary">{{ summary }}</slot>
        </span>
        <DownOutlined v-if="hasDetail" class="row-chevron" />
      </component>
    </div>
    <div v-if="hasDetail && expanded" class="row-detail">
      <!-- 常驻正文而非悬停 tooltip：键盘与触屏用户同样可读（WCAG 1.4.13） -->
      <p v-if="hint" class="row-hint">{{ hint }}</p>
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { DownOutlined } from '@ant-design/icons-vue'

withDefaults(
  defineProps<{
    name: string
    summary?: string
    checked: boolean
    disabled?: boolean
    hasDetail?: boolean
    hint?: string
    toggleable?: boolean
  }>(),
  { summary: '', disabled: false, hasDetail: true, hint: '', toggleable: true }
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

.row-hint {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ant-color-text-tertiary);
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
