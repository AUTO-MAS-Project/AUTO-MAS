<template>
  <div class="baah-table-wrapper" @keydown.esc="requestClose">
    <a-table
      :columns="columns"
      :data-source="rows"
      row-key="field"
      :pagination="false"
      class="config-table baah-table"
      size="small"
      bordered
      :scroll="{ x: 'max-content' }"
    >
      <template #bodyCell="{ column, record }">
        <a-tooltip v-if="column.key === 'fieldName'" :title="t('plan.baah.rowStateHint')">
          {{ record.fieldName }}
        </a-tooltip>
        <a-popover
          v-else
          :open="isEditing(column.key, record.field)"
          trigger="click"
          placement="right"
          :destroy-tooltip-on-hide="true"
          :overlay-style="{ zIndex: 990 }"
          @open-change="handleOpenChange($event, column.key, record.field)"
        >
          <template #content>
            <!-- 只挂载当前格的编辑器，31 天也不常驻数百个下拉控件 -->
            <BAAHCellEditor
              v-if="editor && isEditing(column.key, record.field)"
              :field="editor.field"
              :day-title="columnTitle(editor.key)"
              :state="editor.state"
              :values="editor.values"
              :saving="saving"
              :save-error="saveError"
              :save-error-reason="saveErrorReason"
              @update:state="editor.state = $event"
              @update:values="editor.values = $event"
              @save="saveEditor"
              @cancel="closeEditor"
              @escape="requestClose"
            />
          </template>
          <button
            type="button"
            class="baah-cell"
            :class="[
              `baah-cell-${record[column.key].state}`,
              { 'baah-cell-active': isEditing(column.key, record.field) },
            ]"
            :disabled="isColumnDisabled(column.key)"
            :aria-label="`${record.fieldName} ${columnTitle(column.key)} ${record[column.key].primary} ${record[column.key].secondary}`"
            :aria-expanded="isEditing(column.key, record.field)"
            aria-haspopup="dialog"
            @click="rememberTrigger"
          >
            <span class="baah-cell-primary">{{ record[column.key].primary }}</span>
            <span v-if="record[column.key].secondary" class="baah-cell-secondary">
              {{ record[column.key].secondary }}
            </span>
          </button>
        </a-popover>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { PlanChangeHandler } from '@/utils/planTypeRegistry'
import {
  BAAH_PLAN_KEY_FIELDS,
  applyFieldState,
  readDayFields,
  readFieldState,
  readFieldValues,
  type BAAHFieldState,
  type BAAHKeyFieldName,
} from '@/utils/baahPlanKey'
import {
  planColumnKeys,
  planColumnPath,
  planDayLabel,
  readPlanColumn,
  type PlanMode,
} from '@/utils/planDays'
import { baahCellSummary } from './baahPlanDisplay'
import BAAHCellEditor from './BAAHCellEditor.vue'

const { t } = useI18n()
const props = defineProps<{
  tableData: Record<string, any> | null
  currentMode: PlanMode
  /** BAAH 六类共用摘要表，不提供转置的简化视图。 */
  viewMode: 'config' | 'simple'
  planId?: string
  interactionDisabled?: boolean
  handlePlanChange: PlanChangeHandler
}>()

interface CellDraft {
  key: string
  field: BAAHKeyFieldName
  state: BAAHFieldState
  values: number[]
  initialState: BAAHFieldState
  initialValues: number[]
}

const editor = ref<CellDraft | null>(null)
const saving = ref(false)
const saveError = ref(false)
const saveErrorReason = ref('')
let triggerButton: HTMLElement | null = null
let clickedButton: HTMLElement | null = null

// 全局和周计划始终保留每天及七个星期列，只有轮换模式改为数字天键。
const columnKeys = computed(() =>
  planColumnKeys(props.currentMode, props.tableData?.Info?.RotateDays)
)
const columnTitle = (key: string) =>
  key === 'ALL' ? t('plan.week.ALL') : t(planDayLabel(key).key, planDayLabel(key).params)
const columns = computed(() => [
  { title: t('plan.table.field'), key: 'fieldName', width: 140, fixed: 'left' },
  ...columnKeys.value.map(key => ({ title: columnTitle(key), key, width: 160 })),
])
const dayFields = computed(() =>
  Object.fromEntries(
    columnKeys.value.map(key => [key, readDayFields(readPlanColumn(props.tableData, key))])
  )
)
const rows = computed(() =>
  BAAH_PLAN_KEY_FIELDS.map(field => ({
    field: field.field,
    fieldName: t(field.labelKey),
    ...Object.fromEntries(
      columnKeys.value.map(key => [key, baahCellSummary(dayFields.value[key], field.field, t)])
    ),
  }))
)
const isColumnDisabled = (key: string) =>
  props.interactionDisabled || (props.currentMode === 'ALL' ? key !== 'ALL' : key === 'ALL')
const isEditing = (key: string, field: BAAHKeyFieldName) =>
  editor.value?.key === key && editor.value.field === field
const isDirty = computed(() => {
  const draft = editor.value
  if (!draft) return false
  return (
    draft.state !== draft.initialState ||
    (draft.state === 'on' &&
      draft.values.some((value, index) => value !== draft.initialValues[index]))
  )
})

const rememberTrigger = (event: MouseEvent) => {
  clickedButton = event.currentTarget as HTMLElement
}
const closeEditor = (restoreFocus = true) => {
  if (saving.value) return
  editor.value = null
  saveError.value = false
  saveErrorReason.value = ''
  if (restoreFocus) triggerButton?.focus()
}

/** 未保存或正在保存时阻止切格、切模式、切计划和离开页面。取消按钮才明确丢弃草稿。 */
const beforeLeave = () => {
  if (saving.value || isDirty.value) {
    message.warning(t(saving.value ? 'plan.baah.savingHint' : 'plan.baah.unsavedHint'))
    return false
  }
  closeEditor(false)
  return true
}
const requestClose = () => {
  if (saving.value || isDirty.value) {
    message.warning(t(saving.value ? 'plan.baah.savingHint' : 'plan.baah.unsavedHint'))
    return
  }
  closeEditor()
}
const handleOpenChange = (open: boolean, key: string, field: BAAHKeyFieldName) => {
  if (!open) {
    if (isEditing(key, field)) requestClose()
    return
  }
  if (isColumnDisabled(key) || isEditing(key, field) || !beforeLeave()) return
  triggerButton = clickedButton
  const fields = dayFields.value[key]
  const state = readFieldState(fields, field)
  const values = readFieldValues(fields, field)
  editor.value = {
    key,
    field,
    state,
    values,
    initialState: state,
    initialValues: [...values],
  }
  saveError.value = false
}

const saveEditor = async () => {
  const draft = editor.value
  if (!draft || saving.value) return
  saving.value = true
  saveError.value = false
  saveErrorReason.value = ''
  // 后端按「天 → Key」整份覆写；必须带上其余五类及未编辑的可选尾位。
  const nextFields = applyFieldState(dayFields.value[draft.key], draft.field, draft.state)
  if (draft.state === 'on') nextFields[draft.field] = [...draft.values]
  try {
    const saved = await props.handlePlanChange(planColumnPath(draft.key, 'Key'), nextFields, {
      refresh: false,
      onError: reason => {
        saveErrorReason.value = reason
      },
    })
    saveError.value = !saved
  } catch (error) {
    saveError.value = true
    saveErrorReason.value = error instanceof Error ? error.message : String(error)
  } finally {
    saving.value = false
  }
  if (!saveError.value) closeEditor()
}

defineExpose({ beforeLeave })
</script>

<style scoped>
.baah-table-wrapper {
  overflow: hidden;
}
.baah-table :deep(.ant-table-cell) {
  vertical-align: middle;
}
.baah-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 3px;
  width: 100%;
  min-height: 46px;
  padding: 6px 8px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text);
  text-align: left;
  cursor: pointer;
}
.baah-cell:hover:not(:disabled),
.baah-cell-active {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}
.baah-cell:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 1px;
}
.baah-cell-primary {
  font-weight: 500;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.baah-cell-secondary,
.baah-cell-off {
  color: var(--ant-color-text-secondary);
}
.baah-cell-auto .baah-cell-primary {
  color: var(--ant-color-primary);
}
.baah-cell:disabled,
.baah-cell:disabled .baah-cell-primary,
.baah-cell:disabled .baah-cell-secondary {
  color: var(--ant-color-text-disabled);
  cursor: default;
}
</style>
