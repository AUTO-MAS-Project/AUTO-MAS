<template>
  <div class="event-plan-editor">
    <a-alert
      v-if="!placeholder && itemOptionsError"
      :message="itemOptionsError"
      type="warning"
      show-icon
    />
    <div v-if="activityLoading" class="activity-loading">
      <a-spin size="small" />
      <span>{{ t('core.eventDepotPreview.loading') }}</span>
    </div>
    <a-alert v-if="activityError" :message="activityError" type="warning" show-icon>
      <template #action>
        <a-button
          size="small"
          :loading="activityLoading"
          :disabled="loading"
          @click="emit('retryActivity')"
        >
          {{ t('core.eventDepotPreview.retry') }}
        </a-button>
      </template>
    </a-alert>
    <a-alert
      v-if="placeholder"
      :message="t('core.eventDepotPreview.placeholderHint')"
      type="info"
      show-icon
    />
    <div v-if="rows.length" class="plan-scroll">
      <div class="plan-grid-header">
        <span />
        <span>{{ t('core.eventDepotPreview.stageColumn') }}</span>
        <span>{{ t('core.edit.item') }}</span>
        <span>{{ t('core.edit.targetStock') }}</span>
        <span>
          <a-tooltip :title="stockColumnTitle"
            ><span>{{ t('core.edit.stock') }}</span></a-tooltip
          >
        </span>
      </div>
      <div
        v-for="row in rows"
        :key="row.identity"
        class="plan-row"
        :class="{ 'is-skipped': !row.farmed }"
      >
        <a-checkbox
          :checked="row.farmed"
          :disabled="loading"
          :aria-label="t('core.eventDepotPreview.farmStage')"
          @change="toggleFarm(row, $event.target.checked)"
        />
        <span class="event-stage-text">
          <span class="stage-name">{{ row.stage?.Display ?? stageKindOf(row) }}</span>
          <span v-if="row.stage" class="stage-kind">{{ stageKindOf(row) }}</span>
        </span>
        <span class="event-item-text" :title="row.stage ? itemTextOf(row.stage) : undefined">{{
          row.stage ? itemTextOf(row.stage) : '—'
        }}</span>
        <a-input-number
          :value="row.target"
          :disabled="loading"
          :min="1"
          :precision="0"
          :aria-label="t('core.edit.targetStock')"
          @change="setStageTarget(row, $event)"
        />
        <span class="stock-value">{{
          row.stage ? (inventory[eventDepotItemId(row.stage)] ?? '—') : '—'
        }}</span>
      </div>
    </div>
    <NoData
      v-else
      :description="t('core.eventDepotPreview.noActivity')"
      :image-style="{ height: '48px' }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  eventDepotItemId,
  eventDepotPlanIdentity,
  eventStageIdentity,
  getEventDepotStages,
  getEventOrundumStages,
} from './eventDepotMaintainPresets'
import type { ActivityItem } from '@/types/home'
import type {
  DepotMaintainPlanEditorState,
  DepotMaintainPlanRow,
} from './useDepotMaintainPlanEditor'

type StageKind = 'material' | 'orundum'
type EventRow = {
  identity: string
  type: StageKind
  index: number
  stage?: ActivityItem
  plan?: DepotMaintainPlanRow
  farmed: boolean
  target: number
}

const props = defineProps<{
  editor: DepotMaintainPlanEditorState
  loading: boolean
  stages: ActivityItem[]
  template?: StageKind[]
  activityLoading: boolean
  activityError: string
  itemOptions: { label: string; value: string }[]
  itemOptionsError: string
  inventory: Record<string, number>
  depotInventoryTime: string
}>()
const emit = defineEmits<{ retryActivity: [] }>()
const { t } = useI18n()
const { plans, ensureEventPlan, savePlans, queueSave } = props.editor
const materialStages = computed(() => getEventDepotStages(props.stages))
const orundumStages = computed(() => getEventOrundumStages(props.stages))
const placeholder = computed(() => !props.stages.length && !!props.template?.length)
const stockColumnTitle = computed(() =>
  props.depotInventoryTime
    ? t('core.edit.stockRecognizedAt', { time: props.depotInventoryTime })
    : t('core.edit.stock')
)

// 上期只提供行结构，目标和勾选仍绑定同一份按类别、序号保存的配置。
const rows = computed<EventRow[]>(() => {
  const saved = new Map(
    plans.value
      .filter(plan => plan.StageType !== 'all')
      .map(plan => [eventDepotPlanIdentity(plan), plan])
  )
  const allRow = plans.value.find(plan => plan.StageType === 'all')
  const result: EventRow[] = []
  for (const type of ['material', 'orundum'] as const) {
    const stages = type === 'material' ? materialStages.value : orundumStages.value
    const count = placeholder.value
      ? props.template!.filter(kind => kind === type).length
      : stages.length
    for (let i = 0; i < count; i++) {
      const identity = eventStageIdentity(type, i + 1)
      const plan = saved.get(identity)
      const preset =
        type === 'orundum' ? (allRow?.OrundumDropCount ?? 9999) : (allRow?.DropCount ?? 999)
      result.push({
        identity,
        type,
        index: i + 1,
        stage: placeholder.value ? undefined : stages[i],
        plan,
        farmed: !plan?.Skip,
        target: plan
          ? type === 'orundum'
            ? (plan.OrundumDropCount ?? plan.DropCount)
            : plan.DropCount
          : preset,
      })
    }
  }
  return result
})

// 保留旧配置的当期补齐行为；仅查看占位不会自动新增、保存目标。
watch(
  () => [props.stages, props.activityLoading, props.activityError] as const,
  () => {
    if (props.loading || props.activityLoading || props.activityError || placeholder.value) return
    if (plans.value.some(plan => plan.StageType === 'all')) return
    let added = false
    for (const row of rows.value) {
      if (row.plan) continue
      ensureEventPlan({ StageType: row.type, StageIndex: row.index, DropCount: row.target })
      added = true
    }
    if (added) savePlans()
  },
  { immediate: true }
)

const stageKindOf = (row: EventRow) =>
  row.type === 'orundum'
    ? t('core.eventDepotPreview.orundumStage')
    : t('core.eventDepotPreview.stageIndex', { n: row.index })
const itemTextOf = (stage: ActivityItem) =>
  props.itemOptions.find(option => option.value === eventDepotItemId(stage))?.label ??
  stage.DropName

const toggleFarm = (row: EventRow, farmed: boolean) => {
  const plan = ensureEventPlan({
    StageType: row.type,
    StageIndex: row.index,
    DropCount: row.target,
  })
  if (farmed) delete plan.Skip
  else plan.Skip = true
  savePlans()
}
const setStageTarget = (row: EventRow, value: number | string | null) => {
  const next = Math.max(1, Math.trunc(Number(value) || 1))
  const plan = ensureEventPlan({ StageType: row.type, StageIndex: row.index, DropCount: next })
  if (row.type === 'orundum' && plan.OrundumDropCount !== undefined) plan.OrundumDropCount = next
  else plan.DropCount = next
  queueSave()
}
</script>

<style scoped>
.event-plan-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.activity-loading {
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
}
.plan-scroll {
  overflow-x: auto;
}
.plan-grid-header,
.plan-row {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) minmax(0, 1.2fr) 116px 88px;
  min-width: 560px;
  gap: 8px;
  align-items: center;
}
.plan-grid-header {
  padding: 4px 0 8px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}
.plan-row {
  padding: 4px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}
.event-item-text {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.event-stage-text {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.stage-kind {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}
.stage-name {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-weight: 500;
}
.is-skipped .stage-name,
.is-skipped .event-item-text,
.stock-value {
  color: var(--ant-color-text-secondary);
  font-weight: 400;
}
:deep(.ant-input-number) {
  width: 100%;
}
</style>
