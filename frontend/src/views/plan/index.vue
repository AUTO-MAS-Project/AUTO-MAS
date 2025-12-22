<template>
  <!-- 加载状态 -->
  <div>
    <div v-if="loading" class="loading-container">
      <a-spin size="large" tip="加载中，请稍候..." />
    </div>

    <!-- 主要内容 -->
    <div v-else class="plans-main">
      <!-- 页面头部 -->
      <PlanHeader :plan-list="planList" :active-plan-id="activePlanId" @add-plan="handleAddPlan"
        @remove-plan="handleRemovePlan" />

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
        <PlanSelector :plan-list="planList" :active-plan-id="activePlanId" @plan-change="onPlanChange" />

        <!-- 计划配置 -->
        <PlanConfig :current-plan-name="currentPlanName" :current-mode="currentMode" :view-mode="viewMode"
          :is-editing-plan-name="isEditingPlanName" @update:current-plan-name="currentPlanName = $event"
          @update:current-mode="currentMode = $event" @update:view-mode="viewMode = $event"
          @start-edit-plan-name="startEditPlanName" @finish-edit-plan-name="finishEditPlanName"
          @mode-change="onModeChange">
          <!-- 动态渲染不同类型的表格 -->
          <component :is="currentTableComponent" :table-data="tableData" :current-mode="currentMode"
            :view-mode="viewMode" :options-loaded="!loading" :plan-id="activePlanId"
            :handle-plan-change="handlePlanChange" />
        </PlanConfig>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { getLogger } from '@/utils/logger'
import { usePlanApi } from '@/composables/usePlanApi'
import { generateUniquePlanName, getPlanTypeLabel, validatePlanName } from '@/utils/planNameUtils'
import PlanHeader from './components/PlanHeader.vue'
import PlanSelector from './components/PlanSelector.vue'
import PlanConfig from './components/PlanConfig.vue'
import MaaPlanTable from './tables/MaaPlanTable.vue'
// import GeneralPlanTable from './tables/GeneralPlanTable.vue'
// import CustomPlanTable from './tables/CustomPlanTable.vue'

const logger = getLogger('计划管理')

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
  // 统一使用 MaaPlanConfig 作为默认类型
  const planType = currentPlan?.type
  switch (planType) {
    case 'MaaPlanConfig':
      return MaaPlanTable
    default:
      return MaaPlanTable
  }
})

const handleAddPlan = async (planType: string = 'MaaPlanConfig') => {
  try {
    const response = await createPlan(planType)
    const uniqueName = getDefaultPlanName(planType)
    const newPlan = { id: response.planId, name: uniqueName, type: planType }
    planList.value.push(newPlan)
    activePlanId.value = newPlan.id
    currentPlanName.value = uniqueName
    await loadPlanData(newPlan.id)
    // 如果生成的名称包含数字，说明有重名，提示用户
    if (uniqueName.match(/\s\d+$/)) {
      message.info(
        `已创建新的${getPlanTypeLabel(planType)}："${uniqueName}"，建议您修改为更有意义的名称`,
        4
      )
    } else {
      message.success(`已创建新的${getPlanTypeLabel(planType)}："${uniqueName}"`)
    }
  } catch (error) {
    logger.error('添加计划失败:', error)
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
    logger.error('删除计划失败:', error)
  }
}

// 使用即时保存 - 只发送修改的字段（遵循最小原则）
const savePlanField = async (changes: Record<string, any>): Promise<boolean> => {
  if (!activePlanId.value) {
    return false
  }

  try {
    logger.debug(`保存字段 (${activePlanId.value}):`, changes)
    await updatePlan(activePlanId.value, changes)
    return true
  } catch (error) {
    logger.error('保存计划字段失败:', error)
    return false
  }
}

// 刷新计划数据
const refreshPlanData = async () => {
  if (!activePlanId.value) return

  try {
    const response = await getPlans(activePlanId.value)
    const planData = response.data[activePlanId.value]
    if (planData) {
      currentPlanData.value = response.data
      tableData.value = { ...planData, _isInitialLoad: true }

      if (planData.Info) {
        currentMode.value = planData.Info.Mode || 'ALL'
        const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
        if (currentPlan && planData.Info.Name) {
          currentPlanName.value = planData.Info.Name
        }
      }
    }
  } catch (error) {
    logger.error('刷新计划数据失败:', error)
  }
}

// 处理计划字段变更 - 遵循设置页面的模式
const handlePlanChange = async (path: string, value: any) => {
  // 构建只包含修改字段的更新数据
  const changes = buildNestedObject(path, value)
  const success = await savePlanField(changes)

  // 更新成功后重新获取最新配置
  if (success) {
    await refreshPlanData()
  }
}

// 辅助函数：根据路径构建嵌套对象
// 例如 "Info.Name" -> { Info: { Name: value } }
// 例如 "Monday.stages.stage_1" -> { Monday: { stages: { stage_1: value } } }
const buildNestedObject = (path: string, value: any): Record<string, any> => {
  const keys = path.split('.')
  const result: Record<string, any> = {}
  let current = result

  for (let i = 0; i < keys.length - 1; i++) {
    current[keys[i]] = {}
    current = current[keys[i]]
  }

  current[keys[keys.length - 1]] = value
  return result
}

// 优化计划切换逻辑
const onPlanChange = async (planId: string) => {
  if (planId === activePlanId.value) return

  try {
    // 立即切换到新计划
    logger.info(`切换到新计划: ${planId}`)
    activePlanId.value = planId
    await loadPlanData(planId)
  } catch (error) {
    logger.error('切换计划失败:', error)
  }
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

const finishEditPlanName = async () => {
  if (activePlanId.value) {
    const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
    if (currentPlan) {
      const newName = currentPlanName.value?.trim() || ''
      const existingNames = planList.value.map(plan => plan.name)

      // 验证新名称
      const validation = validatePlanName(newName, existingNames, currentPlan.name)

      if (!validation.isValid) {
        // 如果验证失败，显示错误消息并恢复原名称
        message.error(validation.message || '计划表名称无效')
        currentPlanName.value = currentPlan.name
      } else {
        // 如果验证成功，更新名称并保存到后端
        currentPlan.name = newName
        currentPlanName.value = newName
        // 只发送修改的字段
        await handlePlanChange('Info.Name', newName)
      }
    }
  }
  isEditingPlanName.value = false
}

const onModeChange = async () => {
  // 只发送修改的字段
  await handlePlanChange('Info.Mode', currentMode.value)
}

const loadPlanData = async (planId: string) => {
  try {
    // 总是从后端重新加载数据，确保数据一致性
    const response = await getPlans(planId)
    currentPlanData.value = response.data
    const planData = response.data[planId] as PlanData
    logger.info(`从后端加载数据 (${planId})`)

    if (planData) {
      if (planData.Info) {
        const apiName = planData.Info.Name || ''
        const currentPlan = planList.value.find(plan => plan.id === planId)

        // 优先使用planList中的名称
        if (currentPlan && currentPlan.name) {
          currentPlanName.value = currentPlan.name

          if (apiName !== currentPlan.name) {
            logger.info(`同步名称: API="${apiName}" -> planList="${currentPlan.name}"`)
          }
        } else if (apiName) {
          currentPlanName.value = apiName
          if (currentPlan) {
            currentPlan.name = apiName
          }
        }

        currentMode.value = planData.Info.Mode || 'ALL'
      }

      // 标记这是初始加载，需要强制更新自定义关卡
      tableData.value = { ...planData, _isInitialLoad: true }
    }
  } catch (error) {
    logger.error('加载计划数据失败:', error)
  }
}

const initPlans = async () => {
  try {
    const response = await getPlans()
    if (response.index && response.index.length > 0) {
      // 优化：预先收集所有名称，避免O(n²)复杂度
      const allPlanNames: string[] = []

      planList.value = response.index.map((item: any) => {
        const planId = item.uid
        const planData = response.data[planId]
        const planType = item.type
        let planName = planData?.Info?.Name || ''

        // 如果API中没有名称，或者名称是默认的模板名称，则生成唯一名称
        if (
          !planName ||
          planName === '新 MAA 计划表' ||
          planName === '新通用计划表' ||
          planName === '新自定义计划表'
        ) {
          planName = generateUniquePlanName(planType, allPlanNames)
        }

        allPlanNames.push(planName)
        return { id: planId, name: planName, type: planType }
      })

      const queryPlanId = (route.query.planId as string) || ''
      const target = queryPlanId ? planList.value.find(p => p.id === queryPlanId) : null
      const selectedPlanId = target ? target.id : planList.value[0].id

      // 优化：直接使用已获取的数据，避免重复API调用
      activePlanId.value = selectedPlanId
      const planData = response.data[selectedPlanId]
      if (planData) {
        currentPlanData.value = response.data

        // 直接设置数据，避免loadPlanData的重复调用
        const selectedPlan = planList.value.find(plan => plan.id === selectedPlanId)
        if (selectedPlan) {
          currentPlanName.value = selectedPlan.name
        }

        if (planData.Info) {
          currentMode.value = planData.Info.Mode || 'ALL'
        }

        logger.info(`初始加载数据 (${selectedPlanId})`)
        // 标记这是初始加载，需要强制更新自定义关卡
        tableData.value = { ...planData, _isInitialLoad: true }
      }
    } else {
      currentPlanData.value = null
    }
  } catch (error) {
    logger.error('初始化计划失败:', error)
    currentPlanData.value = null
  } finally {
    loading.value = false
  }
}

const getDefaultPlanName = (planType: string) => {
  // 保持原来的逻辑，但添加重名检测
  const existingNames = planList.value.map(plan => plan.name)
  return generateUniquePlanName(planType, existingNames)
}
// getPlanTypeLabel 现在从 @/utils/planNameUtils 导入，删除本地定义

// 注意：currentPlanName 和 currentMode 的变更保存由各自的 finish/change 事件处理
// 直接调用 handlePlanChange 只发送修改的字段

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

onUnmounted(() => {
  // 组件卸载时的清理逻辑
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
