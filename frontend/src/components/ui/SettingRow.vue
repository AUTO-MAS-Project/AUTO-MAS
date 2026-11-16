<script setup lang="ts">
/**
 * 卡片内的一行设置：左侧标签（可带 ⓘ 提示），右侧控件。
 *
 * 用行而不是栅格，是为了让「标签 → 控件」的对应关系固定，选项多少都不改变排版；
 * 需要独占一行的控件（选项卡片、长输入）传 stacked。
 */
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

withDefaults(
  defineProps<{
    /** 行标签；用 #label 插槽时可以省略 */
    label?: string
    /** 标签后的补充提示 */
    hint?: string
    description?: string
    /** 控件另起一行、左对齐（选项卡片、长输入等） */
    stacked?: boolean
    /** 从属于上一行的子项：缩进 + 细连接线 */
    child?: boolean
    /** 依赖项未启用时整行置灰（控件自身仍需 disabled） */
    disabled?: boolean
  }>(),
  {
    label: '',
    hint: undefined,
    description: undefined,
    stacked: false,
    child: false,
    disabled: false,
  }
)
</script>

<template>
  <div
    class="ui-row"
    :class="{
      'ui-row--stacked': stacked || (!label && !$slots.label),
      'ui-row--child': child,
      'ui-row--disabled': disabled,
    }"
  >
    <div v-if="label || $slots.label" class="ui-row-label">
      <slot name="label">
        <FieldLabelWithHint :text="label" :hint="hint" variant="form" />
      </slot>
      <p v-if="description" class="ui-row-description">{{ description }}</p>
    </div>
    <div class="ui-row-control">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.ui-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(240px, 320px);
  gap: 32px;
  align-items: center;
  min-height: 64px;
  padding: 13px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.ui-row:last-child {
  border-bottom: 0;
}

.ui-row-label {
  min-width: 0;
}

.ui-row-label :deep(.field-label-form) {
  font-weight: 500;
}

.ui-row-description {
  margin: 4px 0 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 19px;
}

.ui-row-control {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-width: 0;
}

.ui-row--stacked {
  grid-template-columns: minmax(0, 1fr);
  align-items: start;
  gap: 8px;
}

.ui-row--stacked .ui-row-control {
  justify-content: flex-start;
}

/* 从属行：缩进 22px 并画一段细连接线，让「从属于上一行」读得出来而不是纯缩进。 */
.ui-row--child .ui-row-label {
  position: relative;
  padding-left: 22px;
}

.ui-row--child .ui-row-label::before {
  content: '';
  position: absolute;
  top: 10px;
  left: 0;
  width: 9px;
  height: 1px;
  background: var(--ant-color-border);
}

.ui-row--child .ui-row-label :deep(.field-label-form) {
  color: var(--ant-color-text-secondary);
  font-weight: 500;
}

.ui-row--disabled .ui-row-label :deep(.field-label-form),
.ui-row--disabled .ui-row-description {
  color: var(--ant-color-text-quaternary);
}

.ui-row--disabled .ui-row-label::before {
  opacity: 0.4;
}

.settings-card-grid .ui-row:not(.ui-row--stacked) {
  grid-template-columns: minmax(0, 1fr) minmax(180px, 240px);
  min-height: 58px;
  gap: 20px;
  padding-block: 12px;
}

.about-settings .ui-row:not(.ui-row--stacked) {
  grid-template-columns: minmax(160px, 1fr) minmax(0, 1.35fr);
  min-height: 54px;
  gap: 24px;
  padding-block: 10px;
}

@container (max-width: 560px) {
  .ui-row,
  .settings-card-grid .ui-row:not(.ui-row--stacked),
  .about-settings .ui-row:not(.ui-row--stacked) {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
  }

  .ui-row-control {
    justify-content: flex-start;
  }
}
</style>
