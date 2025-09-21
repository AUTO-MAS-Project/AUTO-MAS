<template>
  <!-- 加载状态 -->
  <div v-if="loading" class="loading-container">
    <a-spin size="large" tip="加载中，请稍候..." />
  </div>

  <!-- 主要内容 -->
  <div v-else class="plans-main">
    <!-- 页面头部 -->
    <PlanHeader
      :plan-list="planList"
      :active-plan-id="activePlanId"
      @add-plan="handleAddPlan"
      @remove-plan="handleRemovePlan"
    />

    <!-- 空状态 -->
    <div v-if="!planList.length || !currentPlanData" class="empty-state">
      <div class="empty-content">
        <div class="empty-image-container">
          <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image" />
        </div>
        <div class="empty-text-content">
          <h3 class="empty-title">暂无计划</h3>
          <p class="empty-description">您还没有创建任何计划</p>
        </div>
      </div>
    </div>

    <!-- 计划内容 -->
    <div v-else class="plans-content">
      <!-- 计划选择器 -->
      <PlanSelector
        :plan-list="planList"
        :active-plan-id="activePlanId"
        @plan-change="onPlanChange"
      />

      <!-- 计划配置 -->
      <PlanConfig
        :current-plan-name="currentPlanName"
        :current-mode="currentMode"
        :view-mode="viewMode"
        :is-editing-plan-name="isEditingPlanName"
        @update:current-plan-name="currentPlanName = $event"
        @update:current-mode="currentMode = $event"
        @update:view-mode="viewMode = $event"
        @start-edit-plan-name="startEditPlanName"
        @finish-edit-plan-name="finishEditPlanName"
        @mode-change="onModeChange"
      >
        <!-- 动态渲染不同类型的表格 -->
        <component
          :is="currentTableComponent"
          :table-data="tableData"
          :current-mode="currentMode"
          :view-mode="viewMode"
          @update-table-data="handleTableDataUpdate"
        />
      </PlanConfig>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { usePlanApi } from '@/composables/usePlanApi'
import PlanHeader from './components/PlanHeader.vue'
import PlanSelector from './components/PlanSelector.vue'
import PlanConfig from './components/PlanConfig.vue'
import MaaPlanTable from './tables/MaaPlanTable.vue'
// import GeneralPlanTable from './tables/GeneralPlanTable.vue'
// import CustomPlanTable from './tables/CustomPlanTable.vue'

interface PlanData {
  [key: string]: any

  Info?: {
    Mode: 'ALL' | 'Weekly'
    Name: string
    Type?: string
  }
}

const { getPlans, createPlan, updatePlan, deletePlan } = usePlanApi()
const route = useRoute()

const planList = ref<Array<{ id: string; name: string; type: string }>>([])
const activePlanId = ref<string>('')
const currentPlanData = ref<PlanData | null>(null)

const currentPlanName = ref<string>('')
const currentMode = ref<'ALL' | 'Weekly'>('ALL')
const viewMode = ref<'config' | 'simple'>('config')

const isEditingPlanName = ref<boolean>(false)
const loading = ref(true)

// Use a record to match child component expectations
const tableData = ref<Record<string, any>>({})

const currentTableComponent = computed(() => {
  const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
  const planType = currentPlan?.type || 'MaaPlan'
  switch (planType) {
    case 'MaaPlan':
      return MaaPlanTable
    default:
      return MaaPlanTable
  }
})

const handleAddPlan = async (planType: string = 'MaaPlan') => {
  try {
    const response = await createPlan(planType)
    const defaultName = getDefaultPlanName(planType)
    const newPlan = { id: response.planId, name: defaultName, type: planType }
    planList.value.push(newPlan)
    activePlanId.value = newPlan.id
    currentPlanName.value = defaultName
    await loadPlanData(newPlan.id)
    message.info(`已创建新的${getPlanTypeLabel(planType)}，建议您修改为更有意义的名称`, 3)
  } catch (error) {
    console.error('添加计划失败:', error)
  }
}

const handleRemovePlan = async (planId: string) => {
  try {
    await deletePlan(planId)
    const index = planList.value.findIndex(plan => plan.id === planId)
    if (index > -1) {
      planList.value.splice(index, 1)
      if (activePlanId.value === planId) {
        activePlanId.value = planList.value[0]?.id || ''
        if (activePlanId.value) {
          await loadPlanData(activePlanId.value)
        } else {
          currentPlanData.value = null
        }
      }
    }
  } catch (error) {
    console.error('删除计划失败:', error)
  }
}

const onPlanChange = async (planId: string) => {
  activePlanId.value = planId
  await loadPlanData(planId)
}

const startEditPlanName = () => {
  isEditingPlanName.value = true
  setTimeout(() => {
    const input = document.querySelector('.plan-title-input input') as HTMLInputElement
    if (input) {
      input.focus()
      input.select()
    }
  }, 100)
}

const finishEditPlanName = () => {
  isEditingPlanName.value = false
  if (activePlanId.value) {
    const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
    if (currentPlan) {
      currentPlan.name = currentPlanName.value || getDefaultPlanName(currentPlan.type)
    }
  }
}

const onModeChange = () => {
  handleSave()
}

const handleTableDataUpdate = async (newData: Record<string, any>) => {
  tableData.value = newData
  await nextTick()
  handleSave()
}

const loadPlanData = async (planId: string) => {
  try {
    const response = await getPlans(planId)
    currentPlanData.value = response.data
    if (response.data && response.data[planId]) {
      const planData = response.data[planId] as PlanData
      if (planData.Info) {
        const apiName = planData.Info.Name || ''
        if (!apiName && !currentPlanName.value) {
          const currentPlan = planList.value.find(plan => plan.id === planId)
          if (currentPlan) currentPlanName.value = currentPlan.name
        } else if (apiName) {
          currentPlanName.value = apiName
        }
        currentMode.value = planData.Info.Mode || 'ALL'
      }
      tableData.value = planData
    }
  } catch (error) {
    console.error('加载计划数据失败:', error)
  }
}

const initPlans = async () => {
  try {
    const response = await getPlans()
    if (response.index && response.index.length > 0) {
      planList.value = response.index.map((item: any, index: number) => {
        const planId = item.uid
        const planData = response.data[planId]
        const planType = planData?.Info?.Type || 'MaaPlan'
        const planName = planData?.Info?.Name || getDefaultPlanName(planType)
        return { id: planId, name: planName, type: planType }
      })
      const queryPlanId = (route.query.planId as string) || ''
      const target = queryPlanId ? planList.value.find(p => p.id === queryPlanId) : null
      activePlanId.value = target ? target.id : planList.value[0].id
      await loadPlanData(activePlanId.value)
    } else {
      currentPlanData.value = null
    }
  } catch (error) {
    console.error('初始化计划失败:', error)
    currentPlanData.value = null
  } finally {
    loading.value = false
  }
}

const savePlanData = async () => {
  if (!activePlanId.value) return
  try {
    const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
    const planType = currentPlan?.type || 'MaaPlan'

    // Start from existing tableData, then overwrite Info explicitly
    const planData: Record<string, any> = { ...(tableData.value || {}) }
    planData.Info = { Mode: currentMode.value, Name: currentPlanName.value, Type: planType }

    await updatePlan(activePlanId.value, planData)
  } catch (error) {
    console.error('保存计划数据失败:', error)
    throw error
  }
}

const handleSave = async () => {
  if (!activePlanId.value) {
    message.warning('请先选择一个计划')
    return
  }
  try {
    await savePlanData()
  } catch (error) {
    message.error('保存失败')
  }
}

const getDefaultPlanName = (planType: string) =>
  (
    ({
      MaaPlan: '新 MAA 计划表',
      GeneralPlan: '新通用计划表',
      CustomPlan: '新自定义计划表',
    }) as Record<string, string>
  )[planType] || '新计划表'
const getPlanTypeLabel = (planType: string) =>
  (
    ({
      MaaPlan: 'MAA计划表',
      GeneralPlan: '通用计划表',
      CustomPlan: '自定义计划表',
    }) as Record<string, string>
  )[planType] || '计划表'

watch(
  () => [currentPlanName.value, currentMode.value],
  async () => {
    await nextTick()
    handleSave()
  }
)

watch(
  () => route.query.planId,
  async newPlanId => {
    if (!newPlanId) return
    const target = planList.value.find(p => p.id === newPlanId)
    if (target && target.id !== activePlanId.value) {
      activePlanId.value = target.id
      await loadPlanData(activePlanId.value)
    }
  }
)

onMounted(() => {
  initPlans()
})
</script>

<style scoped>
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.plans-main {
  margin: 0 auto;
}

/* 空状态样式 */
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 500px;
  padding: 60px 20px;
  background: linear-gradient(135deg, rgba(24, 144, 255, 0.02), rgba(24, 144, 255, 0.01));
  border-radius: 16px;
  margin: 20px 0;
}

.empty-content {
  text-align: center;
  max-width: 480px;
  animation: fadeInUp 0.8s ease-out;
}

.empty-image-container {
  position: relative;
  margin-bottom: 32px;
  display: inline-block;
}

.empty-image-container::before {
  content: '';
  position: absolute;
  top: -20px;
  left: -20px;
  right: -20px;
  bottom: -20px;
  background: radial-gradient(circle, rgba(24, 144, 255, 0.1) 0%, transparent 70%);
  border-radius: 50%;
  animation: pulse 3s ease-in-out infinite;
}

.empty-image {
  max-width: 200px;
  height: auto;
  opacity: 0.9;
  filter: drop-shadow(0 8px 24px rgba(0, 0, 0, 0.1));
  transition: all 0.3s ease;
  position: relative;
  z-index: 1;
}

.empty-image:hover {
  transform: translateY(-4px);
  filter: drop-shadow(0 12px 32px rgba(0, 0, 0, 0.15));
}

.empty-text-content {
  margin-top: 16px;
}

.empty-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0 0 12px 0;
  background: linear-gradient(135deg, var(--ant-color-text), var(--ant-color-text-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.empty-description {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
  margin: 0;
  opacity: 0.8;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

.plans-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
</style>
