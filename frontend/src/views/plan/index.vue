<template>
  <!-- Lane 8：统一 loading / error / empty / data 状态 -->
  <div class="plan-page">
    <!-- 主要内容 -->
    <div class="plans-main">
      <!-- 页面头部 -->
      <PlanHeader
        :plan-list="planList"
        :active-plan-id="activePlanId"
        :copy-loading="copyLoading"
        @add-plan="handleAddPlan"
        @remove-plan="handleRemovePlan"
        @copy-plan="handleCopyPlan"
      />

      <!-- 加载状态（仅首屏） -->
      <div v-if="loading && !currentPlanData" class="loading-container">
        <a-spin size="large" tip="加载中，请稍候..." />
      </div>

      <!-- 错误状态保留计划页标题与操作上下文 -->
      <div v-else-if="loadError" class="error-state">
        <a-result status="error" title="计划列表加载失败" :sub-title="loadError">
          <template #extra>
            <a-button type="primary" @click="initPlans">重试</a-button>
          </template>
        </a-result>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!planList.length || !currentPlanData" class="empty-state">
        <EmptyState
          compact
          title="暂无计划"
          description="使用上方“新建计划”选择类型，确认后开始配置。"
        />
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
          <a-result
            v-if="unsupportedPlanType"
            status="warning"
            title="当前版本不支持编辑此计划类型"
            :sub-title="`后端返回的计划类型为 ${unsupportedPlanType}，请升级对应前端或检查计划配置。`"
          />

          <!-- 动态渲染已注册类型的表格 -->
          <component
            :is="currentTableComponent"
            v-else
            :table-data="tableData"
            :current-mode="currentMode"
            :view-mode="viewMode"
            :options-loaded="!loading"
            :plan-id="activePlanId"
            :handle-plan-change="handlePlanChange"
          />
        </PlanConfig>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { usePlanApi } from '@/composables/usePlanApi'
import { generateUniquePlanName, getPlanTypeLabel, validatePlanName } from '@/utils/planNameUtils'
import { resolvePlanTableComponent } from '@/utils/planTypeRegistry'
import PlanHeader from './components/PlanHeader.vue'
import PlanSelector from './components/PlanSelector.vue'
import PlanConfig from './components/PlanConfig.vue'
import MaaPlanTable from './tables/MaaPlanTable.vue'
import EmptyState from '@/components/v6/EmptyState.vue'

const logger = window.electronAPI.getLogger('计划管理')

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
// Lane 8：跟踪上次成功同步到后端的模式，用于 onModeChange 失败时回滚 currentMode。
const lastSyncedMode = ref<'ALL' | 'Weekly'>('ALL')
const viewMode = ref<'config' | 'simple'>('config')

const isEditingPlanName = ref<boolean>(false)
const loading = ref(true)
// Lane 8：统一 error 状态
const loadError = ref<string>('')
// Lane 8：复制计划 loading
const copyLoading = ref(false)

// Use a record to match child component expectations
const tableData = ref<Record<string, any>>({})

const currentTableComponent = computed(() => {
  const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
  const planType = currentPlan?.type
  // 类型缺失时不渲染任何表格，由 unsupportedPlanType 提示用户
  if (!planType) return null
  const componentKey = resolvePlanTableComponent(planType)
  switch (componentKey) {
    case 'MaaPlanTable':
      return MaaPlanTable
    default:
      return null
  }
})

const unsupportedPlanType = computed(() => {
  const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
  // 类型缺失视为不支持，避免静默降级为 MaaPlan
  if (!currentPlan?.type) return '(未指定类型)'
  return resolvePlanTableComponent(currentPlan.type) === 'UnknownPlanTable' ? currentPlan.type : ''
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
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加计划失败: ${errorMsg}`)
    message.error(`添加计划失败: ${errorMsg}`)
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
    message.success('计划已删除')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除计划失败: ${errorMsg}`)
    message.error(`删除计划失败: ${errorMsg}`)
  }
}

/**
 * Lane 8：复制当前计划。
 *
 * 流程：
 * 1. 读取源计划完整数据
 * 2. 创建新计划（同类型）
 * 3. 将源计划数据（去除 Info.Name）写入新计划
 * 4. 切换到新计划
 *
 * 后端没有专门的复制接口，因此使用 create + update 组合实现。
 */
const handleCopyPlan = async (sourcePlanId: string) => {
  if (!sourcePlanId || copyLoading.value) return
  copyLoading.value = true
  let createdPlanId = ''
  try {
    // 1. 读取源计划数据
    const sourceResponse = await getPlans(sourcePlanId)
    const sourcePlan = sourceResponse.data[sourcePlanId]
    if (!sourcePlan) {
      throw new Error('源计划数据不存在')
    }

    // 2. 找到源计划类型
    const sourcePlanItem = sourceResponse.index.find((item: any) => item.uid === sourcePlanId)
    const planType = sourcePlanItem?.type || 'MaaPlanConfig'

    // 3. 创建新计划
    const createResponse = await createPlan(planType)
    const newPlanId = createResponse.planId
    createdPlanId = newPlanId

    // 4. 准备复制数据：保留 Mode、所有天数据，但重命名
    const copyData = JSON.parse(JSON.stringify(sourcePlan))
    if (copyData.Info) {
      // 生成唯一名称
      const existingNames = planList.value.map(p => p.name)
      const baseName = copyData.Info.Name || '计划副本'
      let copyName = `${baseName} 副本`
      let counter = 1
      while (existingNames.includes(copyName)) {
        copyName = `${baseName} 副本 ${counter}`
        counter++
      }
      copyData.Info.Name = copyName
    }

    // 5. 更新新计划数据
    await updatePlan(newPlanId, copyData)

    // 6. 加入 planList 并切换
    const newName = copyData.Info?.Name || '计划副本'
    const newPlan = { id: newPlanId, name: newName, type: planType }
    planList.value.push(newPlan)
    activePlanId.value = newPlanId
    currentPlanName.value = newName
    await loadPlanData(newPlanId)

    message.success(`已复制为「${newName}」`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制计划失败: ${errorMsg}`)
    let cleanupFailed = false
    if (createdPlanId) {
      try {
        await deletePlan(createdPlanId)
      } catch (cleanupError) {
        cleanupFailed = true
        const cleanupMessage =
          cleanupError instanceof Error ? cleanupError.message : String(cleanupError)
        logger.error(`清理复制失败产生的计划 ${createdPlanId} 失败: ${cleanupMessage}`)
      }
    }
    message.error(
      cleanupFailed
        ? `复制计划失败，且临时计划 ${createdPlanId} 未能自动清理，请手动删除`
        : `复制计划失败: ${errorMsg}`
    )
  } finally {
    copyLoading.value = false
  }
}

// 使用即时保存 - 只发送修改的字段（遵循最小原则）
const savePlanField = async (changes: Record<string, any>): Promise<boolean> => {
  if (!activePlanId.value) {
    return false
  }

  try {
    logger.debug(`保存字段 (${activePlanId.value}): ${JSON.stringify(changes)}`)
    await updatePlan(activePlanId.value, changes)
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存计划字段失败: ${errorMsg}`)
    return false
  }
}

interface PlanChangeOptions {
  refresh?: boolean
  // 仅在初次加载或切换计划时强制推断自定义关卡。
  // 普通保存刷新需要保留当前定义，避免未被选中的自定义关卡被清空。
  forceCustomStages?: boolean
}

// 刷新计划数据
const refreshPlanData = async (forceCustomStages = false) => {
  if (!activePlanId.value) return

  try {
    const response = await getPlans(activePlanId.value)
    const planData = response.data[activePlanId.value]
    if (planData) {
      currentPlanData.value = response.data
      tableData.value = { ...planData, _isInitialLoad: forceCustomStages }

      if (planData.Info) {
        currentMode.value = planData.Info.Mode || 'ALL'
        lastSyncedMode.value = currentMode.value
        const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
        if (currentPlan && planData.Info.Name) {
          currentPlanName.value = planData.Info.Name
        }
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`刷新计划数据失败: ${errorMsg}`)
    message.warning('数据已保存，但刷新显示失败，请手动刷新')
  }
}

// 处理计划字段变更 - 遵循设置页面的模式
const handlePlanChange = async (
  path: string,
  value: any,
  options: PlanChangeOptions = {}
): Promise<boolean> => {
  // 构建只包含修改字段的更新数据
  const changes = buildNestedObject(path, value)
  const success = await savePlanField(changes)

  // 更新成功后重新获取最新配置
  if (success && options.refresh !== false) {
    await refreshPlanData(options.forceCustomStages === true)
  }

  return success
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

  // Lane 8：保留旧 activePlanId，加载失败时回滚，避免 UI 指向无数据的新计划。
  const previousPlanId = activePlanId.value
  try {
    // 立即切换到新计划
    logger.info(`切换到新计划: ${planId}`)
    activePlanId.value = planId
    await loadPlanData(planId)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`切换计划失败: ${errorMsg}`)
    // 恢复到之前的计划 ID，避免 UI 状态分裂
    activePlanId.value = previousPlanId
    message.error(`切换计划失败: ${errorMsg}`)
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
  if (!activePlanId.value) {
    isEditingPlanName.value = false
    return
  }
  const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
  if (!currentPlan) {
    isEditingPlanName.value = false
    return
  }
  const newName = currentPlanName.value?.trim() || ''
  const existingNames = planList.value.map(plan => plan.name)

  // 验证新名称
  const validation = validatePlanName(newName, existingNames, currentPlan.name)

  if (!validation.isValid) {
    // 如果验证失败，显示错误消息并恢复原名称
    message.error(validation.message || '计划表名称无效')
    currentPlanName.value = currentPlan.name
    isEditingPlanName.value = false
    return
  }

  // Lane 8：保留旧名称快照，API 失败时回滚 planList 与 currentPlanName。
  // 不在失败时退出编辑模式，让用户可以修改后重试。
  const previousName = currentPlan.name
  // 先提交到后端，成功后再更新本地状态
  const success = await handlePlanChange('Info.Name', newName)
  if (success) {
    currentPlan.name = newName
    currentPlanName.value = newName
    isEditingPlanName.value = false
  } else {
    // 失败：恢复 currentPlanName，保留编辑模式让用户重试
    currentPlanName.value = previousName
    // handlePlanChange 已通过 usePlanApi 的 message.error 提示错误
  }
}

const onModeChange = async () => {
  // Lane 8：currentMode 已通过 v-model 更新为新值。
  // 保留上次成功同步到后端的模式，API 失败时回滚 currentMode，避免 UI 与后端状态分裂。
  const previousMode = lastSyncedMode.value
  const newMode = currentMode.value
  const success = await handlePlanChange('Info.Mode', newMode)
  if (success) {
    lastSyncedMode.value = newMode
  } else {
    // 失败：恢复到上次同步的模式
    currentMode.value = previousMode
    // handlePlanChange 已通过 usePlanApi 的 message.error 提示错误
  }
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
        lastSyncedMode.value = currentMode.value
      }

      // 标记这是初始加载，需要强制更新自定义关卡
      tableData.value = { ...planData, _isInitialLoad: true }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载计划数据失败: ${errorMsg}`)
    // 重新抛出，让调用方的 try/catch 能感知失败并执行回滚或提示
    throw error
  }
}

const initPlans = async () => {
  loading.value = true
  loadError.value = ''
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
          lastSyncedMode.value = currentMode.value
        }

        logger.info(`初始加载数据 (${selectedPlanId})`)
        // 标记这是初始加载，需要强制更新自定义关卡
        tableData.value = { ...planData, _isInitialLoad: true }
      }
    } else {
      currentPlanData.value = null
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`初始化计划失败: ${errorMsg}`)
    const isNetworkError = /failed to fetch|networkerror|load failed/i.test(errorMsg)
    loadError.value = isNetworkError
      ? '无法连接后端服务，请确认 AUTO-MAS 后端已启动后重试'
      : errorMsg || '加载计划列表失败，请检查后端连接'
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
      try {
        activePlanId.value = target.id
        await loadPlanData(activePlanId.value)
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`从路由切换计划失败: ${errorMsg}`)
        message.error(`切换计划失败: ${errorMsg}`)
      }
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
  min-height: 240px;
}

/* Lane 8：错误状态样式 */
.error-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 240px;
  padding: var(--v6-space-6);
}

.plan-page {
  min-width: 0;
  container: plan-page / inline-size;
}

.plans-main {
  min-width: 0;
  margin: 0 auto;
}

/* 空状态样式 */
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 240px;
  padding: var(--v6-space-6);
  background: var(--v6-color-surface-transparent);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  margin: var(--v6-space-4) 0;
  backdrop-filter: var(--v6-backdrop-vibrancy);
}

.plans-content {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-4);
}
</style>
