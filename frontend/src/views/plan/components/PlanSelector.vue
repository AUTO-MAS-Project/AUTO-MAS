<template>
  <a-card class="plan-selector-card" :bordered="false">
    <template #title>
      <div class="card-title">
        <span>计划选择</span>
        <a-tag :color="planList.length > 0 ? 'success' : 'default'">
          {{ planList.length }} 个计划
        </a-tag>
      </div>
    </template>

    <div class="plan-selection-container">
      <!-- 计划按钮组 -->
      <div class="plan-buttons-container">
        <a-space wrap size="middle">
          <a-button
            v-for="plan in planList"
            :key="plan.id"
            :type="activePlanId === plan.id ? 'primary' : 'default'"
            size="large"
            class="plan-button"
            @click="handlePlanClick(plan.id)"
          >
            <span class="plan-name">{{ plan.name }}</span>
            <a-tag v-if="hasMixedPlanTypes()" size="small" color="blue" class="plan-type-tag">
              {{ getPlanTypeLabel(plan.type) }}
            </a-tag>
          </a-button>
        </a-space>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { PLAN_TYPE_REGISTRY, type PlanConfigType } from '@/utils/planTypeRegistry'

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
}>()

const handlePlanClick = (planId: string) => {
  if (planId === props.activePlanId) return
  emit('plan-change', planId)
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
  margin-bottom: 16px;
}

.plan-button {
  flex: 1 1 120px;
  border-radius: 8px;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-name {
  flex: 1;
}

.plan-type-tag {
  margin: 0;
}

/* 深度样式 */
.plan-selector-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 16px 24px;
}
</style>
