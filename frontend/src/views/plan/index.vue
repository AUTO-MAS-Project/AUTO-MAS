<template>
  <!-- 加载状态 -->
  <div>
    <div v-if="loading" class="loading-container">
      <a-spin size="large" :tip="t('core.plan.loading')" />
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
        <NoData :image-style="{ height: '200px' }">
          <template #description>
            <div class="empty-title">{{ t('core.plan.emptyTitle') }}</div>
            <div class="empty-description">{{ t('core.plan.emptyDesc') }}</div>
          </template>
        </NoData>
      </div>

      <!-- 计划内容 -->
      <div v-else class="plans-content">
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
          :rotate-days="currentRotateDays"
          :view-mode="viewMode"
          :supports-simple-view="currentPlanDescriptor.supportsSimpleView"
          :is-editing-plan-name="isEditingPlanName"
          :compact="currentPlan?.type === PLAN_CONFIG_TYPES.BAAH"
          :disabled="planOperationPending"
          @update:current-plan-name="currentPlanName = $event"
          @update:current-mode="onModeChange"
          @update:rotate-days="handleRotateDaysChange"
          @update:view-mode="viewMode = $event"
          @start-edit-plan-name="startEditPlanName"
          @finish-edit-plan-name="finishEditPlanName"
        >
          <!-- 动态渲染不同类型的表格 -->
          <component
            :is="currentPlanDescriptor.tableComponent"
            ref="planTable"
            v-bind="
              currentPlan?.type === PLAN_CONFIG_TYPES.BAAH
                ? { interactionDisabled: planOperationPending }
                : {}
            "
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
import { usePlanFieldSave } from './usePlanFieldSave'
import { useI18n } from 'vue-i18n'
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
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
  PLAN_CONFIG_TYPES,
  isKnownPlanType,
  type PlanChangeOptions,
  type PlanConfigData,
  type PlanConfigType,
} from '@/utils/planTypeRegistry'
import { PLAN_ROTATE_DAYS_DEFAULT, clampRotateDays, type PlanMode } from '@/utils/planDays'
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
const currentMode = ref<PlanMode>('ALL')
const currentRotateDays = ref<number>(PLAN_ROTATE_DAYS_DEFAULT)
const viewMode = ref<'config' | 'simple'>('config')

const isEditingPlanName = ref<boolean>(false)
const loading = ref(true)

const tableData = ref<Record<string, any>>({})
const planTable = ref<{ beforeLeave?: () => boolean } | null>(null)
const planOperationPending = ref(false)
const canLeaveTable = () => planTable.value?.beforeLeave?.() ?? true

onBeforeRouteLeave(() => canLeaveTable())
onBeforeRouteUpdate(
  (to, from) =>
    to.query.planId === from.query.planId || (!planOperationPending.value && canLeaveTable())
)

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
  currentRotateDays.value = clampRotateDays(planData.Info?.RotateDays)
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
  if (planOperationPending.value || !canLeaveTable()) return
  planOperationPending.value = true
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
        t('core.plan.toast.createdHint', {
          type: t(getPlanTypeLabelKey(planType)),
          name: uniqueName,
        }),
        4
      )
    } else {
      message.success(
        t('core.plan.toast.created', {
          type: t(getPlanTypeLabelKey(planType)),
          name: uniqueName,
        })
      )
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加计划失败: ${errorMsg}`)
  } finally {
    planOperationPending.value = false
  }
}

const handleRemovePlan = async (planId: string) => {
  if (planOperationPending.value || !canLeaveTable()) return
  planOperationPending.value = true
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
  } finally {
    planOperationPending.value = false
  }
}

// 使用即时保存 - 只发送修改的字段（遵循最小原则）
const savePlanField = usePlanFieldSave(updatePlan, () =>
  viewMode.value === 'simple' ? 'simple' : 'complex'
)

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
  const success = await savePlanField(planId, changes, options)

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
  if (planOperationPending.value || !canLeaveTable()) return

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
  } catch {
    // 接口层已提示失败原因，这里只把界面顺序退回去
    planList.value = previousPlanList
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
    message.error(
      validation.messageKey ? t(validation.messageKey) : t('core.plan.toast.nameInvalid')
    )
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

const onModeChange = async (mode: PlanMode) => {
  if (mode === currentMode.value || planOperationPending.value || !canLeaveTable()) return
  const previous = currentMode.value
  planOperationPending.value = true
  currentMode.value = mode
  try {
    const saved = await handlePlanChange('Info.Mode', mode)
    if (!saved) currentMode.value = previous
  } finally {
    planOperationPending.value = false
  }
}

/** 改轮换天数：先落到界面让列数立刻跟着变，保存失败再退回原来的天数 */
const handleRotateDaysChange = async (days: number) => {
  if (days === currentRotateDays.value || planOperationPending.value || !canLeaveTable()) return
  const previous = currentRotateDays.value
  planOperationPending.value = true
  currentRotateDays.value = days

  try {
    const saved = await handlePlanChange('Info.RotateDays', days)
    if (!saved) currentRotateDays.value = previous
  } finally {
    planOperationPending.value = false
  }
}

const loadPlanData = async (planId: string, force = false, forceCustomStages = false) => {
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

    syncCurrentPlan(planId, forceCustomStages)
    logger.info(`从后端加载数据 (${planId})`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载计划数据失败: ${errorMsg}`)
  }
}

const initPlans = async () => {
  try {
    const response = await getPlans()
    if (response.code !== 200) {
      throw new Error(response.message || t('core.plan.toast.fetchFailed'))
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

    if (!nextPlanList.length) {
      activePlanId.value = ''
      tableData.value = {}
      return
    }

    const queryPlanId = (route.query.planId as string) || ''
    const target = queryPlanId ? nextPlanList.find(plan => plan.id === queryPlanId) : null
    const selectedPlanId = target?.id ?? nextPlanList[0].id

    syncCurrentPlan(selectedPlanId, true)
    activePlanId.value = selectedPlanId
    logger.info(`初始加载数据 (${selectedPlanId})`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`初始化计划失败: ${errorMsg}`)
    planDataMap.value = {}
    planList.value = []
    activePlanId.value = ''
    tableData.value = {}
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

.plans-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.empty-title {
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 8px;
}
.empty-description {
  color: var(--ant-color-text-secondary);
}
</style>
