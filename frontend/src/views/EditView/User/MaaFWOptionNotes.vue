<template>
  <!-- 多个根节点：几段说明在选项块里和控件是同级，沿用选项块的间距 -->
  <div
    v-if="countHint"
    class="option-count-hint"
    :class="{ 'option-count-hint--warning': countHint.warning }"
  >
    {{ countHint.text }}
  </div>

  <!-- 选中的 case 自己的说明（多选时每个勾选项一段，前面标上是哪一项） -->
  <div
    v-for="caseItem in selectedCaseDescriptions"
    :key="`case:${caseItem.name}`"
    class="case-description"
  >
    <div v-if="option.type === 'checkbox'" class="case-description-label">
      {{ caseItem.label || caseItem.name }}
    </div>
    <MaaFWDescriptionView
      :content="caseItem.description"
      :base-path="basePath"
      class="option-description"
    />
  </div>

  <MaaFWDescriptionView
    v-if="option.description"
    :content="option.description"
    :base-path="basePath"
    class="option-description"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaFWOptionInfo, MaaFWTaskOptionValue } from '@/types/script'
import MaaFWDescriptionView from './MaaFWDescriptionView.vue'
import { getCheckboxCountState } from './maafwOptionConstraints'
import { resolveMaaFWCheckboxValue, selectedMaaFWCasesWithDescription } from './maafwOptionValues'

/**
 * 一个选项控件下方的说明：多选的勾选数要求（min_count / max_count）、选中 case 的说明、
 * 选项自己的说明。只读展示，值的显示口径同编辑器（maafwOptionValues）。
 */

const props = defineProps<{
  option: MaaFWOptionInfo
  /** 这个选项已存的值（没存时按默认 case 解析） */
  value: MaaFWTaskOptionValue | undefined
  /** 说明里的图片按项目目录解析 */
  basePath: string
}>()

const { t } = useI18n()

const selectedCaseDescriptions = computed(() =>
  selectedMaaFWCasesWithDescription(props.option, props.value)
)

const countHint = computed(() => {
  const state = getCheckboxCountState(
    props.option,
    resolveMaaFWCheckboxValue(props.option, props.value)
  )
  if (!state) return null
  let text: string
  if (state.max === null) {
    text = t('core.edit.maafwCheckboxCountMin', { min: state.min })
  } else if (state.min === 0) {
    text = t('core.edit.maafwCheckboxCountMax', { max: state.max })
  } else if (state.min === state.max) {
    text = t('core.edit.maafwCheckboxCountExact', { count: state.min })
  } else {
    text = t('core.edit.maafwCheckboxCountRange', { min: state.min, max: state.max })
  }
  if (state.violation) {
    text += t('core.edit.maafwCheckboxCountCurrent', { count: state.count })
  }
  return { text, warning: state.violation !== null }
})
</script>

<style scoped>
.option-count-hint {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.option-count-hint--warning {
  color: var(--ant-color-warning);
}

.case-description-label {
  margin-bottom: 2px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.option-description {
  color: var(--ant-color-text-secondary);
}
</style>
