<template>
  <div class="plan-editor">
    <draggable v-model="plans" item-key="__key" handle=".plan-drag-handle" class="plan-list">
      <template #item="{ element: plan, index }">
        <div class="plan-item">
          <span
            class="plan-drag-handle"
            :title="t('edit.zzzodDragSortHint')"
            :aria-label="t('edit.zzzodDragSortHint')"
          >
            <span class="drag-dots" aria-hidden="true"></span>
          </span>
          <div class="plan-fields">
            <div v-for="col in visibleColumns(plan)" :key="col.field" class="plan-field">
              <span class="plan-field-label">{{ col.title }}</span>
              <a-select
                v-if="isSelectColumn(col)"
                :value="selectValue(plan, col)"
                :options="columnOptions(col, plan)"
                size="small"
                class="plan-field-control"
                @change="(v: any) => setField(plan, col, v)"
              />
              <a-input-number
                v-else
                :value="plan[col.field]"
                size="small"
                class="plan-field-control"
                @change="(v: any) => setField(plan, col, v)"
              />
            </div>
          </div>
          <div class="plan-item-side">
            <span class="plan-run-times">
              {{ t('edit.zzzodPlanRunTimes', { count: Number(plan.run_times) || 0 }) }}
            </span>
            <a-button
              size="small"
              type="text"
              class="plan-delete"
              :aria-label="t('edit.zzzodPlanDelete')"
              @click="removePlan(index)"
            >
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </div>
        </div>
      </template>
    </draggable>

    <a-button size="small" type="dashed" block class="plan-add" @click="addPlan">
      <template #icon><PlusOutlined /></template>
      {{ t('edit.zzzodPlanAdd') }}
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'

interface PlanColumnMeta {
  field: string
  title: string
  type: 'cascade' | 'select' | 'number' | 'team'
  options?: { label: string; value: string }[]
  showWhen?:
    | { field: string; value: string; not?: boolean }
    | { field: string; value: string; not?: boolean }[]
}

interface PlanMission {
  name: string
  display: string
}

interface PlanMissionType {
  name: string
  display: string
  missions: PlanMission[]
}

interface PlanCategory {
  name: string
  label: string
  mission_types: PlanMissionType[]
}

type PlanItem = Record<string, any>

const props = defineProps<{
  /** 行内字段元数据（type=cascade 按声明顺序钻取训练副本树） */
  columns: PlanColumnMeta[]
  /** 新增行默认值 */
  newItem: PlanItem
  /** 计划列表（v-model） */
  modelValue: PlanItem[]
  /** 「训练」tab 副本级联树 */
  trainCategories: PlanCategory[]
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: PlanItem[]): void }>()

const { t } = useI18n()

const plans = computed<PlanItem[]>({
  get: () => {
    // draggable 需要稳定 item-key：来自后端的行无 __key，就地补一个
    // （保存时后端按字段白名单过滤，__key 不会落盘）
    for (const plan of props.modelValue ?? []) {
      if (!plan.__key) plan.__key = `plan-${Math.random().toString(36).slice(2)}`
    }
    return props.modelValue ?? []
  },
  set: value => emit('update:modelValue', value),
})

// 级联列按声明顺序构成链：第 1 列取分类，第 2 列取类型，第 3 列取关卡
const cascadeCategories = computed(() =>
  props.trainCategories.map(c => ({ label: c.label, value: c.name }))
)

const categoryOf = (plan: PlanItem) =>
  props.trainCategories.find(c => c.name === plan.category_name)

const missionTypeOf = (plan: PlanItem) =>
  categoryOf(plan)?.mission_types.find(mt => mt.name === plan.mission_type_name)

const isSelectColumn = (col: PlanColumnMeta) => col.type !== 'number'

/** 下拉列取值统一字符串化（team 列存量行值为 int，选项 value 为字符串下标） */
const selectValue = (plan: PlanItem, col: PlanColumnMeta) => {
  const v = plan[col.field]
  return v == null ? undefined : String(v)
}

const columnOptions = (col: PlanColumnMeta, plan: PlanItem) => {
  if (col.type === 'cascade') {
    if (col.field === 'mission_type_name') {
      return (categoryOf(plan)?.mission_types ?? []).map(mt => ({
        label: mt.display,
        value: mt.name,
      }))
    }
    if (col.field === 'mission_name') {
      return (missionTypeOf(plan)?.missions ?? []).map(m => ({
        label: m.display,
        value: m.name,
      }))
    }
    return cascadeCategories.value
  }
  return col.options ?? []
}

const visibleColumns = (plan: PlanItem) =>
  props.columns.filter(col => {
    // 级联链上层无选项（如合成电池无类型、类型无关卡）时隐藏下层列
    if (col.type === 'cascade') {
      if (col.field === 'mission_type_name' && !categoryOf(plan)?.mission_types.length) {
        return false
      }
      if (col.field === 'mission_name' && !missionTypeOf(plan)?.missions.length) {
        return false
      }
    }
    // show_when 条件列：单条件或条件列表（全部满足才显示）；not=True 取反
    if (col.showWhen) {
      const conds = Array.isArray(col.showWhen) ? col.showWhen : [col.showWhen]
      const allMatch = conds.every(c => {
        const equals = String(plan[c.field] ?? '') === c.value
        return c.not === true ? !equals : equals
      })
      if (!allMatch) {
        return false
      }
    }
    return true
  })

const setField = (plan: PlanItem, col: PlanColumnMeta, value: any) => {
  if (col.type === 'cascade') {
    if (col.field === 'category_name') {
      plan.category_name = value
      plan.mission_type_name = categoryOf(plan)?.mission_types[0]?.name ?? ''
      plan.mission_name = missionTypeOf(plan)?.missions[0]?.name ?? null
    } else if (col.field === 'mission_type_name') {
      plan.mission_type_name = value
      plan.mission_name = missionTypeOf(plan)?.missions[0]?.name ?? null
    } else {
      plan[col.field] = value
    }
    return
  }
  plan[col.field] = value
}

const addPlan = () => {
  const base = props.newItem ?? {}
  const plan: PlanItem = { ...base, __key: `plan-${Math.random().toString(36).slice(2)}` }
  plan.run_times = 0
  plans.value = [...plans.value, plan]
}

const removePlan = (index: number) => {
  const list = [...plans.value]
  list.splice(index, 1)
  plans.value = list
}
</script>

<style scoped>
.plan-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plan-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plan-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.plan-drag-handle {
  cursor: grab;
  padding: 6px 2px;
  color: var(--ant-color-text-quaternary);
  display: inline-flex;
  align-items: center;
}

.plan-drag-handle:hover {
  color: var(--ant-color-text-secondary);
}

.drag-dots {
  display: inline-block;
  width: 8px;
  height: 14px;
  background-image: radial-gradient(circle, currentColor 1px, transparent 1.2px);
  background-size: 4px 4px;
}

.plan-fields {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  min-width: 0;
}

.plan-field {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.plan-field-label {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

.plan-field-control {
  min-width: 120px;
}

.plan-item-side {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.plan-run-times {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  white-space: nowrap;
}

/* 删除按钮：深红低透明，悬停全透明度（项目约定） */
.plan-delete {
  color: var(--ant-color-error);
  opacity: 0.75;
}

.plan-delete:hover {
  opacity: 1;
  color: var(--ant-color-error);
}

.plan-add {
  margin-top: 2px;
}
</style>
