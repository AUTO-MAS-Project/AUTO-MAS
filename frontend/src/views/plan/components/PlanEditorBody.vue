<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { createReusableTemplate } from '@vueuse/core'
import ConfigEditor from '@/views/plugins/ConfigEditor.vue'
import {
  PLAN_CONFIG_TYPES,
  type getPlanTypeDescriptor,
  type PlanChangeHandler,
} from '@/utils/planTypeRegistry'
import type { PlanMode } from '@/utils/planDays'
import type { PlanListItem } from '../planList'
import PlanConfig from './PlanConfig.vue'
import PlanSelector from './PlanSelector.vue'

const props = defineProps<{
  planList: PlanListItem[]
  plan: PlanListItem | null
  planId: string
  descriptor: ReturnType<typeof getPlanTypeDescriptor>
  hasPanel: boolean
  supportsSchedule: boolean
  tableData: Record<string, unknown>
  mode: PlanMode
  rotateDays: number
  pending: boolean
  rename: (planId: string, name: string) => Promise<boolean>
  changeField: PlanChangeHandler
}>()
const name = defineModel<string>('name', { required: true })
const viewMode = defineModel<'config' | 'simple'>('viewMode', { required: true })
const editingName = defineModel<boolean>('editingName', { required: true })
const emit = defineEmits<{
  select: [id: string]
  reorder: [ids: string[]]
  mode: [mode: PlanMode]
  rotateDays: [days: number]
}>()

const [DefineTable, EditorTable] = createReusableTemplate()
const planTable = ref<{ beforeLeave?: () => boolean | Promise<boolean> } | null>(null)
const pluginEditor = ref<InstanceType<typeof ConfigEditor> | null>(null)
defineExpose({
  beforeLeave: async () =>
    (await (planTable.value?.beforeLeave?.() ?? true)) &&
    (await (pluginEditor.value?.beforeLeave() ?? true)),
})

async function selectViewMode(next: 'config' | 'simple') {
  if (!props.hasPanel || (await (pluginEditor.value?.beforeLeave() ?? true))) viewMode.value = next
}

async function startEditName() {
  editingName.value = true
  await nextTick()
  const input = document.querySelector<HTMLInputElement>('.plan-title-input input')
  input?.focus()
  input?.select()
}

async function finishEditName() {
  if (!editingName.value || !props.plan) return
  editingName.value = false
  const plan = props.plan
  const next = name.value.trim()
  if (next === plan.name || !(await props.rename(plan.id, next))) {
    if (props.planId === plan.id) name.value = plan.name
  }
}
</script>

<template>
  <DefineTable>
    <component
      v-if="descriptor"
      :is="descriptor.tableComponent"
      ref="planTable"
      v-bind="plan?.type === PLAN_CONFIG_TYPES.BAAH ? { interactionDisabled: pending } : {}"
      :table-data="tableData"
      :current-mode="mode"
      :view-mode="viewMode"
      :plan-id="planId"
      :handle-plan-change="changeField"
    />
  </DefineTable>
  <div class="plans-content">
    <PlanSelector
      :plan-list="planList"
      :active-plan-id="planId"
      @plan-change="emit('select', $event)"
      @reorder="emit('reorder', $event)"
      @rename="rename"
    />
    <PlanConfig
      v-model:current-plan-name="name"
      :view-mode="viewMode"
      :current-mode="mode"
      :rotate-days="rotateDays"
      :supports-schedule="supportsSchedule"
      :supports-simple-view="descriptor?.supportsSimpleView ?? false"
      :is-editing-plan-name="editingName"
      :compact="plan?.type === PLAN_CONFIG_TYPES.BAAH"
      :disabled="pending"
      @update:current-mode="emit('mode', $event)"
      @update:rotate-days="emit('rotateDays', $event)"
      @update:view-mode="selectViewMode"
      @start-edit-plan-name="startEditName"
      @finish-edit-plan-name="finishEditName"
    >
      <EditorTable v-if="descriptor && (!hasPanel || viewMode === 'simple')" />
      <ConfigEditor v-else ref="pluginEditor" mode="plan" :plan-id="planId">
        <template v-if="descriptor" #fallback><EditorTable /></template>
      </ConfigEditor>
    </PlanConfig>
  </div>
</template>

<style scoped>
.plans-content {
  display: flex;
  flex-direction: column;
  gap: var(--app-page-content-gap);
}
</style>
