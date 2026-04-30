<template>
  <!-- 加载状态 -->
  <div>
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
          v-if="currentPlanDescriptor"
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
            :is="currentPlanDescriptor.tableComponent"
            :table-data="tableData"
            :current-mode="currentMode"
            :view-mode="viewMode"
            :plan-id="activePlanId"
            :handle-plan-change="handlePlanChange"
          />
        </PlanConfig>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { usePlanApi } from '@/composables/usePlanApi'
import type { PlanIndexItem } from '@/api'
import { generateUniquePlanName, getPlanTypeLabel, validatePlanName } from '@/utils/planNameUtils'
import {
  DEFAULT_PLAN_CONFIG_TYPE,
  PLAN_TYPE_REGISTRY,
  isKnownPlanType,
  type PlanConfigData,
  type PlanConfigType,
} from '@/utils/planTypeRegistry'
import PlanHeader from './components/PlanHeader.vue'
import PlanSelector from './components/PlanSelector.vue'
import PlanConfig from './components/PlanConfig.vue'

defineOptions({
  name: 'PlanManagementView',
})

const logger = window.electronAPI.getLogger('计划管理')

const { getPlans, createPlan, updatePlan, deletePlan } = usePlanApi()
const route = useRoute()

interface PlanListItem {
  id: string
  name: string
  type: PlanConfigType
}

const planList = ref<PlanListItem[]>([])
const activePlanId = ref<string>('')
const planDataMap = ref<Record<string, PlanConfigData>>({})

const currentPlanName = ref<string>('')
const currentMode = ref<'ALL' | 'Weekly'>('ALL')
const viewMode = ref<'config' | 'simple'>('config')

const isEditingPlanName = ref<boolean>(false)
const loading = ref(true)

const tableData = ref<Record<string, any>>({})

const currentPlan = computed(
  () => planList.value.find(plan => plan.id === activePlanId.value) || null
)
const currentPlanData = computed<PlanConfigData | null>(
  () => planDataMap.value[activePlanId.value] ?? null
)
const currentPlanDescriptor = computed(() => {
  if (!currentPlan.value) {
    return null
  }
  return PLAN_TYPE_REGISTRY[currentPlan.value.type]
})

const isActivePlan = (planId: string) => activePlanId.value === planId

const clonePlanData = <T,>(value: T): T => structuredClone(value)

const syncCurrentPlan = (planId: string) => {
  const planData = planDataMap.value[planId]
  if (!planData) {
    tableData.value = {}
    return false
  }

  const currentPlanItem = planList.value.find(plan => plan.id === planId)
  const apiName = planData.Info?.Name || ''

  if (currentPlanItem?.name) {
    currentPlanName.value = currentPlanItem.name
  } else {
    currentPlanName.value = apiName
    if (currentPlanItem && apiName) {
      currentPlanItem.name = apiName
    }
  }

  currentMode.value = planData.Info?.Mode || 'ALL'
  tableData.value = clonePlanData(planData)
  return true
}

const applyLocalPlanChange = (planId: string, path: string, value: any) => {
  const planData = planDataMap.value[planId]
  if (!planData) {
    return
  }

  const nextPlanData = clonePlanData(planData) as Record<string, any>
  const keys = path.split('.')
  let current = nextPlanData

  for (let index = 0; index < keys.length - 1; index += 1) {
    const key = keys[index]
    current[key] = current[key] ?? {}
    current = current[key]
  }

  current[keys[keys.length - 1]] = value
  planDataMap.value = {
    ...planDataMap.value,
    [planId]: nextPlanData as PlanConfigData,
  }
}

const handleAddPlan = async (planType: PlanConfigType = DEFAULT_PLAN_CONFIG_TYPE) => {
  try {
    const response = await createPlan(planType)
    const uniqueName = getDefaultPlanName(planType)
    const newPlan: PlanListItem = { id: response.planId, name: uniqueName, type: planType }
    planDataMap.value = {
      ...planDataMap.value,
      [newPlan.id]: response.data as PlanConfigData,
    }
    planList.value.push(newPlan)
    activePlanId.value = newPlan.id
    const saved = await handlePlanChange('Info.Name', uniqueName, false)
    if (!saved) {
      logger.error(`新计划名称持久化失败: ${newPlan.id} -> ${uniqueName}`)
      newPlan.name = response.data.Info?.Name || uniqueName
    }
    syncCurrentPlan(newPlan.id)
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
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加计划失败: ${errorMsg}`)
  }
}

const handleRemovePlan = async (planId: string) => {
  try {
    await deletePlan(planId)
    const nextPlanData = { ...planDataMap.value }
    delete nextPlanData[planId]
    planDataMap.value = nextPlanData
    const index = planList.value.findIndex(plan => plan.id === planId)
    if (index > -1) {
      planList.value.splice(index, 1)
      if (activePlanId.value === planId) {
        activePlanId.value = planList.value[0]?.id || ''
        if (activePlanId.value) {
          await loadPlanData(activePlanId.value)
        } else {
          currentPlanName.value = ''
          currentMode.value = 'ALL'
          tableData.value = {}
        }
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除计划失败: ${errorMsg}`)
  }
}

// 使用即时保存 - 只发送修改的字段（遵循最小原则）
const savePlanField = async (planId: string, changes: Record<string, any>): Promise<boolean> => {
  if (!planId) {
    return false
  }

  try {
    logger.debug(`保存字段 (${planId}): ${JSON.stringify(changes)}`)
    await updatePlan(planId, changes)
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存计划字段失败: ${errorMsg}`)
    return false
  }
}

const fetchPlanData = async (planId: string): Promise<PlanConfigData | null> => {
  const response = await getPlans(planId)
  const planData = response.data[planId] as PlanConfigData | undefined

  if (!planData) {
    return null
  }

  planDataMap.value = {
    ...planDataMap.value,
    ...response.data,
  }

  return planData
}

const handlePlanChange = async (path: string, value: any, reload?: boolean): Promise<boolean> => {
  const planId = activePlanId.value
  if (!planId) {
    return false
  }

  // 构建只包含修改字段的更新数据
  const changes = buildNestedObject(path, value)
  const shouldReload = reload ?? currentPlanDescriptor.value?.reloadAfterSave ?? true
  const success = await savePlanField(planId, changes)

  if (!success) {
    return false
  }

  applyLocalPlanChange(planId, path, value)
  if (isActivePlan(planId)) {
    syncCurrentPlan(planId)
  }

  if (shouldReload) {
    if (isActivePlan(planId)) {
      await loadPlanData(planId, true)
    } else {
      await fetchPlanData(planId)
    }
  }

  return true
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
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`切换计划失败: ${errorMsg}`)
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

const loadPlanData = async (planId: string, force = false) => {
  try {
    if (!force && isActivePlan(planId) && syncCurrentPlan(planId)) {
      logger.info(`从缓存切换计划 (${planId})`)
      return
    }

    const planData = await fetchPlanData(planId)
    if (!planData) {
      if (isActivePlan(planId)) {
        tableData.value = {}
      }
      return
    }

    if (!isActivePlan(planId)) {
      logger.info(`计划已切换，跳过界面同步 (${planId})`)
      return
    }

    syncCurrentPlan(planId)
    logger.info(`从后端加载数据 (${planId})`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载计划数据失败: ${errorMsg}`)
  }
}

const initPlans = async () => {
  try {
    const response = await getPlans()
    if (response.index && response.index.length > 0) {
      planDataMap.value = response.data
      // 优化：预先收集所有名称，避免O(n²)复杂度
      const allPlanNames: string[] = []

      planList.value = response.index.map((item: PlanIndexItem) => {
        const planId = item.uid
        const planData = response.data[planId] as PlanConfigData | undefined
        const planType = item.type as string
        if (!isKnownPlanType(planType)) {
          throw new Error(`未注册的计划表类型: ${planType}`)
        }
        const planDescriptor = PLAN_TYPE_REGISTRY[planType]
        let planName = planData?.Info?.Name || ''

        // 如果API中没有名称，或者名称是默认的模板名称，则生成唯一名称
        if (!planName || planName === planDescriptor?.defaultName) {
          planName = generateUniquePlanName(planType, allPlanNames)
        }

        allPlanNames.push(planName)
        return { id: planId, name: planName, type: planType }
      })

      const queryPlanId = (route.query.planId as string) || ''
      const target = queryPlanId ? planList.value.find(p => p.id === queryPlanId) : null
      const selectedPlanId = target ? target.id : planList.value[0].id

      activePlanId.value = selectedPlanId
      syncCurrentPlan(selectedPlanId)
      logger.info(`初始加载数据 (${selectedPlanId})`)
    } else {
      planDataMap.value = {}
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`初始化计划失败: ${errorMsg}`)
    planDataMap.value = {}
  } finally {
    loading.value = false
  }
}

const getDefaultPlanName = (planType: PlanConfigType) => {
  const existingNames = planList.value.map(plan => plan.name)
  return generateUniquePlanName(planType, existingNames)
}

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
