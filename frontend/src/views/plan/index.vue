<template>
  <!-- 加载状态 -->
  <div>
    <div v-if="loading" class="loading-container">
      <a-spin size="large" :tip="t('plan.loading')" />
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

      <!-- 增删改/排序失败：给可见反馈，而不是只写日志 -->
      <OperationStatusBanner
        v-if="actionError"
        state="error"
        message-key="plan.actionFailed"
        :detail="actionError.detail"
      />

      <!-- 切换计划失败：已退回原计划，这里给一次重试 -->
      <OperationStatusBanner
        v-if="switchError"
        state="error"
        message-key="plan.switchFailed"
        retryable
        :detail="switchError.detail"
        @retry="retryPlanSwitch"
      />

      <!-- 列表请求失败：不能伪装成「没有计划」 -->
      <div v-if="!planList.length && planListError" class="state-block">
        <RetryableErrorState
          :error="planListError"
          message-key="plan.listLoadFailed"
          @retry="initPlans"
        />
      </div>

      <!-- 空状态：确实拉到过空列表才显示 -->
      <div v-else-if="!planList.length" class="empty-state">
        <div class="empty-content">
          <div class="empty-image-container">
            <img src="@/assets/NoData.png" :alt="t('plan.noData')" class="empty-image" />
          </div>
          <div class="empty-text-content">
            <h3 class="empty-title">{{ t('plan.emptyTitle') }}</h3>
            <p class="empty-description">{{ t('plan.emptyDesc') }}</p>
          </div>
        </div>
      </div>

      <!-- 当前计划详情没拉到：给恢复动作，不显示一份空表 -->
      <div v-else-if="!currentPlanData" class="state-block">
        <RetryableErrorState
          v-if="planDetailError"
          :error="planDetailError"
          message-key="plan.detailLoadFailed"
          @retry="reloadActivePlan"
        />
        <a-spin v-else size="large" :tip="t('plan.loading')" />
      </div>

      <!-- 计划内容 -->
      <div v-else class="plans-content">
        <OperationStatusBanner
          v-if="planListState === 'error_with_previous_data'"
          state="warning"
          message-key="plan.staleList"
          retryable
          :detail="planListError?.detail"
          @retry="initPlans"
        />
        <OperationStatusBanner
          v-if="planDetailError"
          state="warning"
          message-key="plan.staleDetail"
          retryable
          :detail="planDetailError.detail"
          @retry="reloadActivePlan"
        />

        <!-- 计划选择器 -->
        <PlanSelector
          :plan-list="planList"
          :active-plan-id="activePlanId"
          @plan-change="onPlanChange"
          @reorder="handlePlanReorder"
          @rename="renamePlan"
        />

        <!-- 计划配置 -->
        <PlanConfig
          v-if="currentPlanDescriptor"
          :current-plan-name="currentPlanName"
          :current-mode="currentMode"
          :view-mode="viewMode"
          :supports-simple-view="currentPlanDescriptor.supportsSimpleView"
          :supports-layout-mode="currentPlanDescriptor.supportsLayoutMode"
          :baah-layout="baahLayout"
          :is-editing-plan-name="isEditingPlanName"
          @update:current-plan-name="currentPlanName = $event"
          @update:current-mode="currentMode = $event"
          @update:view-mode="viewMode = $event"
          @update:baah-layout="baahLayout = $event"
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
            :baah-layout="baahLayout"
            :plan-id="activePlanId"
            :handle-plan-change="handlePlanChange"
          />
        </PlanConfig>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { usePlanApi } from '@/composables/usePlanApi'
import type { PlanIndexItem } from '@/api'
import {
  generateUniquePlanName,
  getPlanTypeLabelKey,
  validatePlanName,
} from '@/utils/planNameUtils'
import {
  DEFAULT_PLAN_CONFIG_TYPE,
  PLAN_TYPE_REGISTRY,
  isKnownPlanType,
  type PlanChangeOptions,
  type PlanConfigData,
  type PlanConfigType,
} from '@/utils/planTypeRegistry'
import { AppRequestError, toAppError } from '@/utils/appError'
import type { PageDataState } from '@/utils/pageDataState'
import OperationStatusBanner from '@/components/OperationStatusBanner.vue'
import RetryableErrorState from '@/components/RetryableErrorState.vue'
import PlanHeader from './components/PlanHeader.vue'
import PlanSelector from './components/PlanSelector.vue'
import PlanConfig from './components/PlanConfig.vue'

const { t } = useI18n()

defineOptions({
  name: 'PlanManagementView',
})

const logger = window.electronAPI.getLogger('计划管理')

const { getPlans, createPlan, updatePlan, deletePlan, reorderPlans } = usePlanApi()
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
// BAAH 计划表的关卡安排：每天一类（默认，三行各管一件事）或多类混打（六类都填）。
// 与 viewMode 一样只是当前页面的显示状态，各计划表共用同一个选择
const baahLayout = ref<'mixed' | 'single'>('single')

const isEditingPlanName = ref<boolean>(false)
const loading = ref(true)

const tableData = ref<Record<string, any>>({})

// 计划列表/详情的加载状态：空数组只代表「确实没有计划」，失败单独记录
const planListState = ref<PageDataState>('not_loaded')
const planListError = ref<AppRequestError | null>(null)
const planDetailError = ref<AppRequestError | null>(null)
// 切换计划失败：已退回原计划，保留目标 id 供重试
const switchError = ref<AppRequestError | null>(null)
const switchTargetId = ref<string>('')
// 增删改/排序等一次性动作的失败：给用户可见反馈，而不是只写日志
const actionError = ref<AppRequestError | null>(null)

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

const clonePlanData = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

const syncCurrentPlan = (planId: string, forceCustomStages = false) => {
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
  tableData.value = { ...clonePlanData(planData), _isInitialLoad: forceCustomStages }
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
  actionError.value = null
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
        t('plan.toast.createdHint', {
          type: t(getPlanTypeLabelKey(planType)),
          name: uniqueName,
        }),
        4
      )
    } else {
      message.success(
        t('plan.toast.created', {
          type: t(getPlanTypeLabelKey(planType)),
          name: uniqueName,
        })
      )
    }
  } catch (error) {
    const appError = toAppError(error)
    logger.error(`添加计划失败: ${appError.detail ?? appError.message}`)
    actionError.value = appError
  }
}

const handleRemovePlan = async (planId: string) => {
  actionError.value = null
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
    const appError = toAppError(error)
    logger.error(`删除计划失败: ${appError.detail ?? appError.message}`)
    actionError.value = appError
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
    actionError.value = null
    return true
  } catch (error) {
    const appError = toAppError(error)
    logger.error(`保存计划字段失败: ${appError.detail ?? appError.message}`)
    actionError.value = appError
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

const handlePlanChange = async (
  path: string,
  value: any,
  reloadOrOptions?: boolean | PlanChangeOptions
): Promise<boolean> => {
  const planId = activePlanId.value
  if (!planId) {
    return false
  }

  // 构建只包含修改字段的更新数据
  const changes = buildNestedObject(path, value)
  const options = typeof reloadOrOptions === 'object' ? reloadOrOptions : undefined
  const shouldReload =
    typeof reloadOrOptions === 'boolean'
      ? reloadOrOptions
      : (options?.refresh ?? currentPlanDescriptor.value?.reloadAfterSave ?? true)
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
      await loadPlanData(planId, true, options?.forceCustomStages === true)
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

  const previousPlanId = activePlanId.value
  switchError.value = null
  switchTargetId.value = ''
  planDetailError.value = null

  // 立即切换到新计划
  logger.info(`切换到新计划: ${planId}`)
  activePlanId.value = planId

  const ok = await loadPlanData(planId)
  // 切换失败：退回原计划，别把用户留在一张空表上
  if (!ok && activePlanId.value === planId) {
    switchError.value = planDetailError.value ?? new AppRequestError('unknown', {})
    switchTargetId.value = planId
    planDetailError.value = null
    activePlanId.value = previousPlanId
    if (previousPlanId) {
      syncCurrentPlan(previousPlanId)
    } else {
      tableData.value = {}
    }
  }
}

// 切换失败后的重试：重新切到刚才没切过去的那个计划
const retryPlanSwitch = () => {
  if (switchTargetId.value) void onPlanChange(switchTargetId.value)
}

/** 排序请求串行化：并发请求会按完成顺序落盘，与界面上的拖拽顺序不一致 */
let reorderTask: Promise<unknown> = Promise.resolve()

/** 拖拽排序结果落盘：界面先就位，保存失败再退回 */
const handlePlanReorder = async (planIds: string[]) => {
  const planById = new Map(planList.value.map(plan => [plan.id, plan]))
  const nextPlanList: PlanListItem[] = []

  for (const planId of planIds) {
    const plan = planById.get(planId)
    // 顺序列表必须是全部计划的完整顺序，缺项说明计划列表已变化，放弃本次排序
    if (!plan) return
    nextPlanList.push(plan)
  }
  if (nextPlanList.length !== planList.value.length) return

  const previousPlanList = planList.value
  planList.value = nextPlanList

  reorderTask = reorderTask.catch(() => undefined).then(() => reorderPlans(planIds))

  try {
    await reorderTask
    actionError.value = null
  } catch (error) {
    // 界面顺序退回去，同时把失败挂到页面上（接口层不再弹 Toast）
    planList.value = previousPlanList
    actionError.value = toAppError(error)
  }
}

/** 改名：校验、落盘、同步本地缓存，返回是否改名成功 */
const renamePlan = async (planId: string, newName: string): Promise<boolean> => {
  const plan = planList.value.find(item => item.id === planId)
  if (!plan) {
    return false
  }

  const existingNames = planList.value.filter(item => item.id !== planId).map(item => item.name)
  const validation = validatePlanName(newName, existingNames, plan.name)

  if (!validation.isValid) {
    message.error(validation.messageKey ? t(validation.messageKey) : t('plan.toast.nameInvalid'))
    return false
  }

  const success = await savePlanField(planId, buildNestedObject('Info.Name', newName))
  if (!success) {
    return false
  }

  plan.name = newName
  applyLocalPlanChange(planId, 'Info.Name', newName)
  if (isActivePlan(planId)) {
    currentPlanName.value = newName
  }
  return true
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
  isEditingPlanName.value = false

  const planId = activePlanId.value
  const currentPlan = planList.value.find(plan => plan.id === planId)
  if (!currentPlan) {
    return
  }

  const newName = currentPlanName.value?.trim() || ''
  if (newName === currentPlan.name) {
    // 只差首尾空格：把标题回写成规范名称，别把多余空格留在界面上
    currentPlanName.value = newName
    return
  }

  const renamed = await renamePlan(planId, newName)
  if (!renamed) {
    // 校验或保存失败：标题退回原名
    currentPlanName.value = currentPlan.name
  }
}

const onModeChange = async () => {
  // 只发送修改的字段
  await handlePlanChange('Info.Mode', currentMode.value)
}

const loadPlanData = async (
  planId: string,
  force = false,
  forceCustomStages = false
): Promise<boolean> => {
  try {
    if (!force && isActivePlan(planId) && syncCurrentPlan(planId)) {
      logger.info(`从缓存切换计划 (${planId})`)
      planDetailError.value = null
      return true
    }

    const planData = await fetchPlanData(planId)
    if (!planData) {
      if (isActivePlan(planId)) {
        tableData.value = {}
        planDetailError.value = new AppRequestError('unknown', {
          detail: `plan data missing: ${planId}`,
        })
      }
      return false
    }

    if (!isActivePlan(planId)) {
      logger.info(`计划已切换，跳过界面同步 (${planId})`)
      return true
    }

    syncCurrentPlan(planId, forceCustomStages)
    planDetailError.value = null
    logger.info(`从后端加载数据 (${planId})`)
    return true
  } catch (error) {
    const appError = toAppError(error)
    logger.error(`加载计划数据失败: ${appError.detail ?? appError.message}`)
    // 保留当前表格数据，只把失败挂出来给用户重试
    if (isActivePlan(planId)) planDetailError.value = appError
    return false
  }
}

// 局部重试：只重拉当前计划的详情
const reloadActivePlan = () => {
  if (!activePlanId.value) return
  return loadPlanData(activePlanId.value, true)
}

const initPlans = async () => {
  loading.value = true
  try {
    const response = await getPlans()
    if (response.code !== 200) {
      throw new Error(response.message || t('plan.toast.fetchFailed'))
    }

    const nextPlanDataMap: Record<string, PlanConfigData> = {}
    const nextPlanList: PlanListItem[] = []
    const allPlanNames: string[] = []

    response.index.forEach((item: PlanIndexItem) => {
      const planId = item.uid
      const planData = response.data[planId] as PlanConfigData | undefined
      const planType = item.type as string

      if (!isKnownPlanType(planType)) {
        logger.error(`跳过未注册的计划表类型: ${planType}`)
        return
      }
      if (!planData) {
        logger.error(`跳过缺少配置数据的计划表: ${planId}`)
        return
      }

      const planDescriptor = PLAN_TYPE_REGISTRY[planType]
      let planName = planData.Info?.Name || ''
      if (!planName || planName === planDescriptor.defaultName) {
        planName = generateUniquePlanName(planType, allPlanNames)
      }

      allPlanNames.push(planName)
      nextPlanDataMap[planId] = planData
      nextPlanList.push({ id: planId, name: planName, type: planType })
    })

    planDataMap.value = nextPlanDataMap
    planList.value = nextPlanList
    planListError.value = null
    actionError.value = null

    if (!nextPlanList.length) {
      activePlanId.value = ''
      tableData.value = {}
      planListState.value = 'empty'
      return
    }
    planListState.value = 'loaded_fresh'

    const queryPlanId = (route.query.planId as string) || ''
    const target = queryPlanId ? nextPlanList.find(plan => plan.id === queryPlanId) : null
    const selectedPlanId = target?.id ?? nextPlanList[0].id

    syncCurrentPlan(selectedPlanId, true)
    activePlanId.value = selectedPlanId
    logger.info(`初始加载数据 (${selectedPlanId})`)
  } catch (error) {
    const appError = toAppError(error)
    logger.error(`初始化计划失败: ${appError.detail ?? appError.message}`)
    // 失败时保留上一次的计划列表，不能把「请求失败」画成「没有计划」
    planListError.value = appError
    planListState.value = planList.value.length ? 'error_with_previous_data' : 'error_without_data'
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
      await onPlanChange(target.id)
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

.state-block {
  padding: 24px;
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
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
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
  background: radial-gradient(circle, var(--ant-color-primary-bg) 0%, transparent 70%);
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
