<template>
  <div class="pipeline-row" :class="{ 'is-off': !checked, 'is-expanded': expanded }">
    <div class="row-head">
      <span class="row-dot" aria-hidden="true" />
      <!-- 开关紧贴任务名：靠邻近性表达「开关管的是这个任务」。无开关的行留占位，保持任务名列对齐 -->
      <span class="switch-slot">
        <a-switch
          v-if="switchable"
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
    switchable?: boolean
  }>(),
  { summary: '', disabled: false, hasDetail: true, hint: '', switchable: true }
)

const emit = defineEmits<{ change: [checked: boolean] }>()

const expanded = ref(false)
</script>

<style scoped>
.pipeline-row {
  position: relative;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.pipeline-row:last-child {
  border-bottom: none;
}

.row-head {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 52px;
  padding: 6px 4px;
}

/* 流水线轨道：圆点 + 向下连接线 */
.row-dot {
  position: relative;
  flex: 0 0 8px;
  width: 8px;
  height: 8px;
  margin-left: 6px;
  border-radius: 50%;
  background: var(--ant-color-primary);
  transition: background 0.2s ease;
}

.row-dot::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 8px;
  width: 1px;
  height: calc(100% + 46px);
  transform: translateX(-50%);
  background: var(--ant-color-border);
}

.pipeline-row:last-child .row-dot::after {
  display: none;
}

.is-off .row-dot {
  background: var(--ant-color-text-quaternary);
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

.switch-slot {
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

.is-off .row-name {
  color: var(--ant-color-text-tertiary);
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

.is-off .row-summary {
  color: var(--ant-color-text-quaternary);
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

.row-detail {
  position: relative;
  padding: 4px 8px 16px 34px;
}

/* 详情区左侧续接流水线轨道，视觉上表明「这些配置属于上面那个任务」 */
.row-detail::before {
  content: '';
  position: absolute;
  left: 14px;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--ant-color-border);
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

  .row-detail::before {
    display: none;
  }
}
</style>
