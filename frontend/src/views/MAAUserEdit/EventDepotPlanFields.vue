<template>
  <a-select
    :value="stageIndex"
    :options="stageOptions"
    :disabled="loading || stages.length === 0"
    show-search
    option-filter-prop="label"
    :virtual="false"
    :get-popup-container="getPopupContainer"
    :popup-match-select-width="false"
    :placeholder="t('edit.pickStage')"
    @change="emit('change', Number($event))"
  />
  <a-select
    class="event-material-display"
    :value="stage?.Drop"
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
import { resolveActivityStage } from './activityStages'

const props = defineProps<{
  stageIndex?: number
  stages: ActivityItem[]
  loading: boolean
  itemOptions: { label: string; value: string }[]
  getPopupContainer: (trigger: HTMLElement) => HTMLElement
}>()
const emit = defineEmits<{ change: [value: number] }>()
const { t } = useI18n()

const stage = computed(() => resolveActivityStage(props.stages, props.stageIndex))
const materialOptions = computed(() =>
  stage.value
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
  const options = props.stages.map((item, index) => ({
    label: `${t('eventDepotPreview.stageIndex', { n: index + 1 })} · ${item.Display}`,
    value: index + 1,
  }))
  if (props.stageIndex && !options.some(option => option.value === props.stageIndex)) {
    const label = t('eventDepotPreview.stageIndex', { n: props.stageIndex })
    options.push({
      value: props.stageIndex,
      label: stage.value
        ? `${label} · ${t('eventDepotPreview.fallbackStage', { stage: stage.value.Value })}`
        : label,
    })
  }
  return options
})
</script>

<style scoped>
/* 材料只读但仍是计划的主要信息，保持正常文本对比度。 */
.event-material-display :deep(.ant-select-selection-item) {
  color: var(--ant-color-text);
}
</style>
