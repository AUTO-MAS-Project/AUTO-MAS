<template>
  <span
    class="goal-current"
    :title="line.currentUnknown ? t('edit.maaCultivateCurrentUnknownHint') : undefined"
    >{{ line.current }}</span
  >
  <a-tag v-if="line.overLimit" color="warning">{{ t('edit.maaCultivateOverLimitShort') }}</a-tag>
  <a-tag v-if="line.state" :color="line.state.color">{{ t(line.state.i18n) }}</a-tag>
  <!-- 达成行不给下拉：静态显示达成档位（占位宽度与下拉一致，保持列对齐） -->
  <span v-if="line.achieved" class="goal-achieved-level">{{ line.levelLabel }}</span>
  <a-select
    v-else
    :value="line.savedLevel || undefined"
    :options="line.options"
    :placeholder="t('edit.maaCultivateGoalNone')"
    allow-clear
    :disabled="disabled"
    :get-popup-container="getPopupContainer"
    :list-height="listHeight"
    class="goal-level"
    :aria-label="line.label"
    @change="(value: unknown) => emit('change', value)"
  />
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { CultivateGoalLine } from './cultivateGoalLines'

defineProps<{
  line: CultivateGoalLine
  disabled: boolean
  getPopupContainer: (trigger: HTMLElement) => HTMLElement
  listHeight: number
}>()

const emit = defineEmits<{ change: [value: unknown] }>()

const { t } = useI18n()
</script>

<style scoped>
.goal-current {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  white-space: nowrap;
}

.goal-achieved-level {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  width: 96px;
  flex-shrink: 0;
  min-height: 24px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

/* 宽度压住父级 :deep(.ant-select){width:100%}，档位下拉固定 96px */
.goal-level {
  width: 96px;
  flex-shrink: 0;
}
</style>
