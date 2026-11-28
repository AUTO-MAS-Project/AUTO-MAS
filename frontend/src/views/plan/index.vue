<template>
  <div>
    <div v-if="loading" class="loading-container">
      <a-spin size="large" :tip="t('core.plan.loading')" />
    </div>

    <div v-else class="plans-main">
      <PlanHeader
        :plan-list="planList"
        :active-plan-id="activePlanId"
        :creating="planOperationPending"
        :remove-plan="handleRemovePlan"
        @add-plan="handleAddPlan"
      />

      <UnavailablePlanCards v-model:items="unavailablePlans" />

      <PlanEmptyState v-if="!planList.length || !currentPlanData" />

      <PlanEditorBody
        v-else
        ref="editorBody"
        v-model:name="currentPlanName"
        v-model:view-mode="viewMode"
        v-model:editing-name="isEditingPlanName"
        :plan-list="planList"
        :plan="currentPlan"
        :plan-id="activePlanId"
        :descriptor="currentPlanDescriptor"
        :has-panel="currentPlanHasPanel"
        :supports-schedule="currentPlanSupportsSchedule"
        :table-data="tableData"
        :mode="currentMode"
        :rotate-days="currentRotateDays"
        :pending="planOperationPending"
        :rename="renamePlan"
        :change-field="handlePlanChange"
        @select="onPlanChange"
        @reorder="handlePlanReorder"
        @mode="onModeChange"
        @rotate-days="handleRotateDaysChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useConfigLoader } from '@/services/configUiSync'
import { buildNestedObject, usePlanFieldSave } from './usePlanFieldSave'
import { useI18n } from 'vue-i18n'
import { computed, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { fetchPluginScriptTypes, usePluginRegistry } from '@/composables/usePluginScriptTypes'
import { indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { usePlanApi } from '@/composables/usePlanApi'
import { nameField, projectPlanList, projectUnavailablePlans, type PlanListItem } from './planList'
import { generateUniquePlanName, validatePlanName } from '@/utils/planNameUtils'
import {
  getPlanTypeDescriptor,
  type PlanChangeOptions,
  type PlanConfigData,
  type PlanTypeOption,
} from '@/utils/planTypeRegistry'
import { PLAN_ROTATE_DAYS_DEFAULT, clampRotateDays, type PlanMode } from '@/utils/planDays'
import PlanHeader from './components/PlanHeader.vue'
import PlanEmptyState from './components/PlanEmptyState.vue'
import UnavailablePlanCards from './components/UnavailablePlanCards.vue'
import type { UnavailableConfigCard } from '@/components/UnavailableConfigCards.vue'
import PlanEditorBody from './components/PlanEditorBody.vue'

const { t } = useI18n()

defineOptions({
  name: 'PlanManagementView',
})

const logger = window.electronAPI.getLogger('计划管理')

const { getPlans, createPlan, updatePlan, deletePlan, reorderPlans } = usePlanApi()
const route = useRoute()

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
const editorBody = ref<InstanceType<typeof PlanEditorBody> | null>(null)
const planOperationPending = ref(false)
// 所属插件不可用的计划表：只读卡片，只能删除
const unavailablePlans = ref<UnavailableConfigCard[]>([])
const canLeaveTable = () => editorBody.value?.beforeLeave() ?? true

// 离开确认可能挂起，放行前再检查是否已有计划操作开始。
const canChangePlan = async () =>
  !planOperationPending.value && (await canLeaveTable()) && !planOperationPending.value

onBeforeRouteLeave(canLeaveTable)
onBeforeRouteUpdate((to, from) => to.query.planId === from.query.planId || canChangePlan())

const currentPlan = computed(
  () => planList.value.find(plan => plan.id === activePlanId.value) || null
)
const currentPlanData = computed(() => planDataMap.value[activePlanId.value] ?? null)
const registry = usePluginRegistry()
const currentPlanHasPanel = computed(() => {
  const type = currentPlan.value?.type ?? ''
  const index = indexPluginScriptTypes(registry.data.value?.data)
  return index.blockPlanConfigTypes.has(type) || index.frontendByPlanConfigType.has(type)
})
const currentPlanDescriptor = computed(() => getPlanTypeDescriptor(currentPlan.value?.type))
const currentPlanSupportsSchedule = computed(
  () => !!currentPlanDescriptor.value || currentPlanData.value?.Info?.Mode != null
)

const isActivePlan = (planId: string) => activePlanId.value === planId

const clonePlanData = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

const syncCurrentPlan = (planId: string, forceCustomStages = false) => {
  const planData = planDataMap.value[planId]
  if (!planData) {
    tableData.value = {}
    return false
  }

  const currentPlanItem = planList.value.find(plan => plan.id === planId)
  const apiName = nameField(planData).value || ''
  if (currentPlanItem && !currentPlanItem.name) currentPlanItem.name = apiName
  currentPlanName.value = currentPlanItem?.name || apiName

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

const handleAddPlan = async (plan: PlanTypeOption, owner?: { scriptId: string }) => {
  if (!(await canChangePlan())) return
  planOperationPending.value = true
  try {
    const response = await createPlan(plan, owner)
    if (response.code !== 200) throw new Error(response.message)
    const uniqueName = generateUniquePlanName(
      plan.defaultName,
      planList.value.map(item => item.name)
    )
    const newPlan: PlanListItem = {
      id: response.planId,
      name: uniqueName,
      type: plan.configType,
      typeLabel: plan.selectorTag,
    }
    planDataMap.value = {
      ...planDataMap.value,
      [newPlan.id]: response.data as PlanConfigData,
    }
    planList.value.push(newPlan)
    activePlanId.value = newPlan.id
    const name = nameField(response.data)
    const saved = await handlePlanChange(name.path, uniqueName, false)
    if (!saved) {
      logger.error(`新计划名称持久化失败: ${newPlan.id} -> ${uniqueName}`)
      newPlan.name = name.value || uniqueName
    }
    syncCurrentPlan(newPlan.id)
    // 如果生成的名称包含数字，说明有重名，提示用户
    const details = { type: plan.displayName, name: uniqueName }
    if (/\s\d+$/.test(uniqueName)) message.info(t('core.plan.toast.createdHint', details), 4)
    else message.success(t('core.plan.toast.created', details))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加计划失败: ${errorMsg}`)
  } finally {
    planOperationPending.value = false
  }
}

const handleRemovePlan = async (planId: string) => {
  if (!(await canChangePlan())) return
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

const selectPlan = async (planId: string) => {
  logger.info(`切换到新计划: ${planId}`)
  activePlanId.value = planId
  await loadPlanData(planId)
}

const onPlanChange = async (planId: string) => {
  if (planId !== activePlanId.value && (await canChangePlan())) await selectPlan(planId)
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

  const { path } = nameField(planDataMap.value[planId])
  const success = await savePlanField(planId, buildNestedObject(path, newName))
  if (!success) {
    return false
  }

  plan.name = newName
  applyLocalPlanChange(planId, path, newName)
  if (isActivePlan(planId)) {
    currentPlanName.value = newName
  }
  return true
}

const onModeChange = async (mode: PlanMode) => {
  if (mode === currentMode.value || !(await canChangePlan())) return
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
  if (days === currentRotateDays.value || !(await canChangePlan())) return
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

const initPlans = useConfigLoader(['config', 'plans'], async read => {
  try {
    const [response, plugins] = await Promise.all([
      getPlans(undefined, { silent: true }),
      fetchPluginScriptTypes(read),
    ])
    read(response)
    if (response.code !== 200) {
      throw new Error(response.message || t('core.plan.toast.fetchFailed'))
    }
    unavailablePlans.value = projectUnavailablePlans(response)

    const { nextPlanDataMap, nextPlanList } = projectPlanList(response, plugins, message =>
      logger.error(message)
    )

    planDataMap.value = nextPlanDataMap
    planList.value = nextPlanList

    if (!nextPlanList.length) {
      activePlanId.value = ''
      tableData.value = {}
      return
    }

    const queryPlanId = (route.query.planId as string) || ''
    const target = queryPlanId ? nextPlanList.find(plan => plan.id === queryPlanId) : null
    const current = nextPlanList.find(plan => plan.id === activePlanId.value)
    const selectedPlanId = current?.id ?? target?.id ?? nextPlanList[0].id

    const draftName = isEditingPlanName.value ? currentPlanName.value : undefined
    syncCurrentPlan(selectedPlanId, selectedPlanId !== activePlanId.value)
    if (draftName !== undefined && selectedPlanId === activePlanId.value) {
      currentPlanName.value = draftName
    }
    activePlanId.value = selectedPlanId
    logger.info(`初始加载数据 (${selectedPlanId})`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`初始化计划失败: ${errorMsg}`)
  } finally {
    loading.value = false
  }
})

watch(
  () => route.query.planId,
  async newPlanId => {
    if (!newPlanId) return
    const target = planList.value.find(p => p.id === newPlanId)
    if (target && target.id !== activePlanId.value) {
      // 路由更新守卫已确认离开当前草稿。
      await selectPlan(target.id)
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
</style>
