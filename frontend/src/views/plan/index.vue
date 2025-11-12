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
            :options-loaded="!loading"
            :plan-id="activePlanId"
            @update-table-data="handleTableDataUpdate"
          />
        </PlanConfig>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { usePlanApi } from '@/composables/usePlanApi'
import { generateUniquePlanName, getPlanTypeLabel, validatePlanName } from '@/utils/planNameUtils'
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
const switching = ref(false) // 添加切换状态

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

// 添加异步保存队列和状态管理
const savingQueue = ref(new Set<string>())
const savePromises = ref(new Map<string, Promise<void>>())

// 异步保存函数
const saveInBackground = async (planId: string) => {
  // 如果已经在保存队列中，等待现有的保存完成
  if (savingQueue.value.has(planId)) {
    const existingPromise = savePromises.value.get(planId)
    if (existingPromise) {
      await existingPromise
    }
    return
  }

  savingQueue.value.add(planId)

  const savePromise = (async () => {
    try {
      const currentPlan = planList.value.find(plan => plan.id === planId)
      const planType = currentPlan?.type || 'MaaPlanConfig'

      // Start from existing tableData, then overwrite Info explicitly
      const planData: Record<string, any> = { ...(tableData.value || {}) }
      planData.Info = { Mode: currentMode.value, Name: currentPlanName.value, Type: planType }

      console.log(`[计划表] 保存数据 (${planId}):`, planData)
      await updatePlan(planId, planData)
    } catch (error) {
      console.error('后台保存计划数据失败:', error)
      // 不显示错误消息，避免打断用户操作
    } finally {
      savingQueue.value.delete(planId)
      savePromises.value.delete(planId)
    }
  })()

  savePromises.value.set(planId, savePromise)
  return savePromise
}

// 使用 VueUse 的 useDebounceFn 替换手写的 debounce
const debouncedSave = useDebounceFn(async () => {
  if (!activePlanId.value) return
  await saveInBackground(activePlanId.value)
}, 300)

const handleSave = async () => {
  if (!activePlanId.value) {
    message.warning('请先选择一个计划')
    return
  }
  await debouncedSave()
}

// 优化计划切换逻辑 - 异步保存，立即切换
const onPlanChange = async (planId: string) => {
  if (planId === activePlanId.value) return

  switching.value = true
  try {
    // 异步保存当前计划，不等待完成
    if (activePlanId.value) {
      saveInBackground(activePlanId.value).catch(error => {
        console.error('切换时保存当前计划失败:', error)
        message.warning('保存当前计划时出现问题，请检查数据是否完整')
      })
    }

    // 立即切换到新计划，提升响应速度
    console.log(`[计划表] 切换到新计划: ${planId}`)
    activePlanId.value = planId
    await loadPlanData(planId)
  } finally {
    switching.value = false
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

const finishEditPlanName = () => {
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
        // 如果验证成功，更新名称
        currentPlan.name = newName
        currentPlanName.value = newName
        // 触发保存操作，确保名称被保存到后端
        handleSave()
      }
    }
  }
  isEditingPlanName.value = false
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
    // 总是从后端重新加载数据，确保数据一致性
    const response = await getPlans(planId)
    currentPlanData.value = response.data
    const planData = response.data[planId] as PlanData
    console.log(`[计划表] 从后端加载数据 (${planId})`)

    if (planData) {
      if (planData.Info) {
        const apiName = planData.Info.Name || ''
        const currentPlan = planList.value.find(plan => plan.id === planId)

        // 优先使用planList中的名称
        if (currentPlan && currentPlan.name) {
          currentPlanName.value = currentPlan.name

          if (apiName !== currentPlan.name) {
            console.log(`[计划表] 同步名称: API="${apiName}" -> planList="${currentPlan.name}"`)
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
    console.error('加载计划数据失败:', error)
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

        console.log(`[计划表] 初始加载数据 (${selectedPlanId}):`, planData)
        // 标记这是初始加载，需要强制更新自定义关卡
        tableData.value = { ...planData, _isInitialLoad: true }
      }
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

const getDefaultPlanName = (planType: string) => {
  // 保持原来的逻辑，但添加重名检测
  const existingNames = planList.value.map(plan => plan.name)
  return generateUniquePlanName(planType, existingNames)
}
// getPlanTypeLabel 现在从 @/utils/planNameUtils 导入，删除本地定义

watch(
  () => [currentPlanName.value, currentMode.value],
  () => {
    // await nextTick()
    debouncedSave() // 直接调用即可，无需等待
  },
  { flush: 'post' }
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

// 在组件卸载前确保所有保存操作完成
const ensureAllSaved = async () => {
  const pendingPromises = Array.from(savePromises.value.values())
  if (pendingPromises.length > 0) {
    await Promise.allSettled(pendingPromises)
  }
}

onMounted(() => {
  initPlans()

  // 监听页面卸载
  window.addEventListener('beforeunload', ensureAllSaved)
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', ensureAllSaved)
  ensureAllSaved()
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
