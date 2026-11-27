<script setup lang="ts">
import { nextTick, ref } from 'vue'
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

const planTable = ref<{ beforeLeave?: () => boolean | Promise<boolean> } | null>(null)
defineExpose({ beforeLeave: () => planTable.value?.beforeLeave?.() ?? true })

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
  <div class="plans-content">
    <PlanSelector
      :plan-list="planList"
      :active-plan-id="planId"
      @plan-change="emit('select', $event)"
      @reorder="emit('reorder', $event)"
      @rename="rename"
    />
    <PlanConfig
      v-if="descriptor"
      v-model:current-plan-name="name"
      v-model:view-mode="viewMode"
      :current-mode="mode"
      :rotate-days="rotateDays"
      :supports-simple-view="descriptor.supportsSimpleView"
      :is-editing-plan-name="editingName"
      :compact="plan?.type === PLAN_CONFIG_TYPES.BAAH"
      :disabled="pending"
      @update:current-mode="emit('mode', $event)"
      @update:rotate-days="emit('rotateDays', $event)"
      @start-edit-plan-name="startEditName"
      @finish-edit-plan-name="finishEditName"
    >
      <component
        :is="descriptor.tableComponent"
        ref="planTable"
        v-bind="plan?.type === PLAN_CONFIG_TYPES.BAAH ? { interactionDisabled: pending } : {}"
        :table-data="tableData"
        :current-mode="mode"
        :view-mode="viewMode"
        :plan-id="planId"
        :handle-plan-change="changeField"
      />
    </PlanConfig>
    <ConfigEditor v-else ref="planTable" mode="plan" :plan-id="planId" />
  </div>
</template>

<style scoped>
.plans-content {
  display: flex;
  flex-direction: column;
  gap: var(--app-page-content-gap);
}
</style>
