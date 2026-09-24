<template>
  <a-card class="plan-selector-card" :bordered="false">
    <template #title>
      <div class="card-title">
        <span>{{ t('plan.selectLabel') }}</span>
        <a-tag :color="planList.length > 0 ? 'success' : 'default'">
          {{ t('plan.count', { count: planList.length }, planList.length) }}
        </a-tag>
      </div>
    </template>

    <div class="plan-selection-container">
      <!-- 计划按钮组：拖手柄换位置，点按钮切计划，点铅笔改名 -->
      <draggable
        :model-value="planList"
        item-key="id"
        :animation="180"
        handle=".plan-drag-handle"
        ghost-class="plan-ghost"
        chosen-class="plan-chosen"
        class="plan-buttons-container"
        @update:model-value="onReorder"
      >
        <template #item="{ element: plan }">
          <div
            class="plan-button"
            :class="{ 'plan-button-active': plan.id === activePlanId }"
            role="button"
            tabindex="0"
            @click="handlePlanClick(plan.id)"
            @keydown.enter.prevent="handlePlanClick(plan.id)"
            @keydown.space.prevent="handlePlanClick(plan.id)"
          >
            <span
              class="plan-drag-handle"
              role="button"
              tabindex="0"
              :aria-label="t('plan.drag')"
              :title="t('plan.drag')"
              @click.stop
            >
              <MenuOutlined />
            </span>

            <a-input
              v-if="editingPlanId === plan.id"
              v-model:value="editingName"
              class="plan-rename-input"
              size="small"
              :maxlength="50"
              :placeholder="t('plan.namePlaceholder')"
              @click.stop
              @press-enter="finishRename"
              @blur="finishRename"
              @keydown.esc="cancelRename"
            />
            <span v-else class="plan-name">{{ plan.name }}</span>

            <a-tag v-if="hasMixedPlanTypes()" size="small" color="blue" class="plan-type-tag">
              {{ getPlanTypeLabel(plan.type) }}
            </a-tag>

            <a-button
              v-if="editingPlanId !== plan.id"
              type="text"
              size="small"
              class="plan-rename-btn"
              :aria-label="t('plan.rename')"
              :title="t('plan.rename')"
              @click.stop="startRename(plan)"
            >
              <template #icon>
                <EditOutlined />
              </template>
            </a-button>
          </div>
        </template>
      </draggable>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditOutlined, MenuOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import { PLAN_TYPE_REGISTRY, type PlanConfigType } from '@/utils/planTypeRegistry'

const { t } = useI18n()

interface Plan {
  id: string
  name: string
  type: PlanConfigType
}

interface Props {
  planList: Plan[]
  activePlanId: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'plan-change': [planId: string]
  reorder: [planIds: string[]]
  rename: [planId: string, name: string]
}>()

/** 正在改名的计划 id，空串表示没有计划处于改名态 */
const editingPlanId = ref('')
const editingName = ref('')

const handlePlanClick = (planId: string) => {
  if (planId === props.activePlanId) return
  emit('plan-change', planId)
}

const onReorder = (plans: Plan[]) => {
  emit(
    'reorder',
    plans.map(plan => plan.id)
  )
}

const startRename = async (plan: Plan) => {
  editingPlanId.value = plan.id
  editingName.value = plan.name
  await nextTick()
  // a-input 无前后缀时 class 落在 input 本体上，有包装时落在容器上
  const input =
    document.querySelector<HTMLInputElement>('input.plan-rename-input') ??
    document.querySelector<HTMLInputElement>('.plan-rename-input input')
  input?.focus()
  input?.select()
}

const finishRename = () => {
  const planId = editingPlanId.value
  if (!planId) return

  const plan = props.planList.find(item => item.id === planId)
  const nextName = editingName.value.trim()
  editingPlanId.value = ''

  // 空名或原名不改：交回原样，由父组件负责校验与提示
  if (!plan || (nextName === plan.name && nextName !== '')) return
  emit('rename', planId, nextName)
}

const cancelRename = () => {
  editingPlanId.value = ''
}

const hasMixedPlanTypes = () => {
  if (props.planList.length <= 1) return false

  const firstType = props.planList[0].type
  return !props.planList.every(plan => plan.type === firstType)
}

const getPlanTypeLabel = (planType: PlanConfigType) => PLAN_TYPE_REGISTRY[planType].selectorTag
</script>

<style scoped>
.plan-selector-card {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 600;
}

.plan-selection-container {
  padding: 16px;
}

.plan-buttons-container {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.plan-button {
  min-width: 140px;
  min-height: 40px;
  padding: 0 8px 0 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.plan-button:hover {
  color: var(--ant-color-primary-hover);
  border-color: var(--ant-color-primary-hover);
}

.plan-button:focus-visible {
  outline: none;
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

.plan-button-active {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary);
  font-weight: 600;
}

.plan-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-drag-handle {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  border-radius: 4px;
  cursor: grab;
  user-select: none;
}

.plan-drag-handle:hover,
.plan-drag-handle:focus-visible {
  color: var(--ant-color-primary);
  outline: none;
}

.plan-drag-handle:active,
.plan-chosen .plan-drag-handle {
  cursor: grabbing;
}

.plan-rename-input {
  flex: 1;
  min-width: 120px;
}

.plan-rename-btn {
  height: 20px;
  padding: 0;
  color: var(--ant-color-text-tertiary);
}

.plan-rename-btn:hover {
  color: var(--ant-color-primary);
}

.plan-type-tag {
  margin: 0;
}

.plan-ghost {
  opacity: 0.35;
}

/* 深度样式 */
.plan-selector-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 16px 24px;
}
</style>
