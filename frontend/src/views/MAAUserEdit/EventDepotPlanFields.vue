<template>
  <a-select
    :value="selection"
    :options="stageOptions"
    :disabled="loading"
    show-search
    option-filter-prop="label"
    :virtual="false"
    :get-popup-container="getPopupContainer"
    :list-height="listHeight"
    :popup-match-select-width="false"
    :placeholder="t('edit.pickStage')"
    @change="onChange(String($event))"
  />
  <a-select
    class="event-material-display"
    :value="materialValue"
    :options="materialOptions"
    disabled
    :placeholder="'—'"
    :aria-label="t('edit.item')"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ActivityItem } from '@/types/home'
import {
  getEventDepotStages,
  getEventOrundumStages,
  resolveEventDepotStage,
  type EventDepotStageType,
} from './eventDepotMaintainPresets'

const props = defineProps<{
  stageIndex?: number
  stageType?: EventDepotStageType
  legacyFallback?: boolean
  stages: ActivityItem[]
  loading: boolean
  itemOptions: { label: string; value: string }[]
  getPopupContainer: (trigger: HTMLElement) => HTMLElement
  listHeight: number
}>()
const emit = defineEmits<{
  change: [value: { StageType: EventDepotStageType; StageIndex?: number }]
}>()
const { t } = useI18n()

const selection = computed(() =>
  props.stageType === 'all' ? 'all:' : `${props.stageType ?? 'material'}:${props.stageIndex ?? ''}`
)
const stage = computed(() =>
  resolveEventDepotStage(props.stages, {
    StageType: props.stageType,
    StageIndex: props.stageIndex,
    LegacyIndex: props.legacyFallback,
  })
)
const materialValue = computed(() => (props.stageType === 'all' ? 'all' : stage.value?.Drop))
const materialOptions = computed(() =>
  props.stageType === 'all'
    ? [{ value: 'all', label: t('eventDepotPreview.allMaterials') }]
    : stage.value
      ? [
          {
            value: stage.value.Drop,
            label:
              props.itemOptions.find(item => item.value === stage.value?.Drop)?.label ??
              stage.value.DropName,
          },
        ]
      : []
)
const stageOptions = computed(() => {
  // 动态模板通过预设新增，避免把旧逐计划药量扩散到多个活动关。
  const options =
    props.stageType === 'all' ? [{ label: t('eventDepotPreview.allStages'), value: 'all:' }] : []
  for (const [type, stages] of [
    ['material', getEventDepotStages(props.stages)],
    ['orundum', getEventOrundumStages(props.stages)],
  ] as const) {
    stages.forEach((item, index) =>
      options.push({
        label: `${t(type === 'material' ? 'eventDepotPreview.stageIndex' : 'eventDepotPreview.orundumIndex', { n: index + 1 })} · ${item.Display}`,
        value: `${type}:${index + 1}`,
      })
    )
  }
  // 完整活动列表序号仅用于展示和保留旧优先选关，不与材料序号混用。
  if (!options.some(option => option.value === selection.value)) {
    const label = t(
      props.stageType === 'activity'
        ? 'eventDepotPreview.legacyIndex'
        : props.stageType === 'orundum'
          ? 'eventDepotPreview.orundumIndex'
          : 'eventDepotPreview.stageIndex',
      { n: props.stageIndex ?? 1 }
    )
    options.push({
      value: selection.value,
      label: stage.value ? `${label} · ${stage.value.Display}` : label,
    })
  }
  return options
})

const onChange = (value: string) => {
  const [type, index] = value.split(':')
  emit('change', {
    StageType: type as EventDepotStageType,
    ...(index ? { StageIndex: Number(index) } : {}),
  })
}
</script>

<style scoped>
/* 材料只读但仍是计划的主要信息，保持正常文本对比度。 */
.event-material-display :deep(.ant-select-selection-item) {
  color: var(--ant-color-text);
}
</style>
