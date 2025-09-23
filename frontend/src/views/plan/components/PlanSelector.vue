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
            @click="handlePlanClick(plan.id)"
            class="plan-button"
          >
            <span class="plan-name">{{ plan.name }}</span>
            <a-tag
              v-if="shouldShowPlanTypeTag(plan)"
              size="small"
              color="blue"
              class="plan-type-tag"
            >
              {{ getPlanTypeLabel(plan.type) }}
            </a-tag>
          </a-button>
        </a-space>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
interface Plan {
  id: string
  name: string
  type: string
}

interface Props {
  planList: Plan[]
  activePlanId: string
}

interface Emits {
  (e: 'plan-change', planId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 防抖点击处理
const debounce = <T extends (...args: any[]) => any>(func: T, wait: number): T => {
  let timeout: NodeJS.Timeout | null = null
  return ((...args: any[]) => {
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(() => func(...args), wait)
  }) as T
}

const handlePlanClick = debounce((planId: string) => {
  if (planId === props.activePlanId) return
  emit('plan-change', planId)
}, 100)

// 判断是否需要显示计划类型标签
// 当所有计划的类型都相同时不显示标签，否则显示非默认类型的标签
const shouldShowPlanTypeTag = (plan: Plan) => {
  // 如果只有一个计划或没有计划，不显示类型标签
  if (props.planList.length <= 1) {
    return false
  }

  // 检查是否所有计划的类型都相同
  const firstType = props.planList[0].type
  const allSameType = props.planList.every(p => p.type === firstType)

  // 如果所有计划类型相同，则不显示任何标签
  return !allSameType
}

const getPlanTypeLabel = (planType: string) => {
  const normalizedPlanType = planType
  const labelMap: Record<string, string> = {
    MaaPlanConfig: 'MAA',
    GeneralPlan: '通用',
    CustomPlan: '自定义',
  }
  return labelMap[normalizedPlanType] || normalizedPlanType
}
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
