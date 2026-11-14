<template>
  <a-select
    :value="null"
    :options="pickerOptions"
    :loading="loading"
    :disabled="disabled || loading || availableOperatorOptions.length === 0"
    :placeholder="operatorPlaceholder"
    :not-found-content="pickerEmptyText"
    show-search
    :filter-option="false"
    :virtual="false"
    :get-popup-container="getPopupContainer"
    :list-height="listHeight"
    class="operator-picker"
    :aria-label="t('plugins.maa_adapter.edit.maaCultivatePickOperators')"
    @search="handleOperatorSearch"
    @change="selectOperator"
  />
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { pinyin } from 'pinyin-pro'
import { usePlanSelectPopup } from './usePlanSelectPopup'
import type { CultivateOperatorCatalogEntry as OperatorCatalogEntry } from './cultivateTargets'

const props = defineProps<{
  operatorCatalog: OperatorCatalogEntry[]
  selectedOperatorIds: string[]
  disabled: boolean
  loading: boolean
}>()
const emit = defineEmits<{ add: [operatorId: string] }>()
const { t } = useI18n()
const { getPopupContainer, listHeight } = usePlanSelectPopup()
const selectOperator = (operatorId: string) => {
  operatorSearch.value = ''
  emit('add', operatorId)
}

// ── 目录选择器：搜索驱动——未输入时不给默认列表（427 条目录无浏览价值），
// 输入后按名称/ID/拼音匹配全量结果；内置过滤关闭，过滤由 pickerOptions 完成 ──
const operatorSearch = ref('')
const handleOperatorSearch = (value: string) => {
  operatorSearch.value = value
}
// 拼音索引：目录加载时一次性预计算全拼与首字母（如 银灰 → yinhui / yh），
// 按目录 value 键存，输入纯拉丁时参与子串匹配
const pickerPinyinIndex = computed(() => {
  const index = new Map<string, { full: string; initials: string }>()
  for (const option of props.operatorCatalog) {
    index.set(option.value, {
      full: pinyin(option.label, { toneType: 'none', type: 'array' }).join('').toLowerCase(),
      initials: pinyin(option.label, {
        pattern: 'first',
        toneType: 'none',
        type: 'array',
      })
        .join('')
        .toLowerCase(),
    })
  }
  return index
})
// 已添加的干员不再出现在选择器里（Set 查找，目录 427 条 × 目标行）；
// 无任何可达目标的干员列出但不可选并说明原因——
// 直接隐藏会让用户以为目录缺人（决策 40）
const selectedOperatorIds = computed(() => new Set(props.selectedOperatorIds))
const noGoalReason = (entry: OperatorCatalogEntry): string =>
  t(
    entry.dataMissing
      ? 'plugins.maa_adapter.edit.maaCultivateNoGoalDataMissing'
      : 'plugins.maa_adapter.edit.maaCultivateNoGoalTier'
  )
const availableOperatorOptions = computed(() =>
  props.operatorCatalog
    .filter(option => !selectedOperatorIds.value.has(option.value))
    .map(option =>
      option.maxElite > 0 ||
      option.maxSkillLevel > 1 ||
      option.skills.length ||
      option.modules.length
        ? { label: option.label, value: option.value }
        : {
            label: `${option.label}（${noGoalReason(option)}）`,
            value: option.value,
            disabled: true,
          }
    )
)
const pickerOptions = computed(() => {
  const text = operatorSearch.value.trim().toLowerCase()
  if (!text) return []
  const pinyinText = /^[a-z0-9]+$/.test(text) ? text : ''
  return availableOperatorOptions.value.filter(option => {
    if (option.label.toLowerCase().includes(text) || option.value.toLowerCase().includes(text)) {
      return true
    }
    const py = pinyinText && pickerPinyinIndex.value.get(option.value)
    return !!py && (py.full.includes(pinyinText) || py.initials.includes(pinyinText))
  })
})
const operatorPlaceholder = computed(() =>
  props.loading
    ? t('plugins.maa_adapter.edit.maaCultivateCatalogLoading')
    : availableOperatorOptions.value.length
      ? t('core.maaCopilot.pickerSearchHint')
      : t('plugins.maa_adapter.edit.maaCultivateNoOperators')
)
// 空输入引导输入，输入后无匹配才报"没有匹配的干员"
const pickerEmptyText = computed(() =>
  operatorSearch.value.trim()
    ? t('plugins.maa_adapter.edit.maaCultivateSearchEmpty')
    : t('core.maaCopilot.pickerSearchHint')
)
</script>
