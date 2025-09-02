<template>
  <!-- 加载状态 -->
  <div v-if="loading" class="loading-container">
    <a-spin size="large" tip="加载中，请稍候..." />
  </div>

  <!-- 主要内容 -->
  <div v-else class="plans-main">
    <!-- 页面头部 -->
    <div class="plans-header">
      <div class="header-left">
        <h1 class="page-title">计划管理</h1>
      </div>
      <div class="header-actions">
        <a-space size="middle">
          <a-button
            type="primary"
            size="large"
            @click="handleAddPlan"
          >
            <template #icon>
              <PlusOutlined />
            </template>
            新建计划
          </a-button>

          <a-popconfirm
            v-if="planList.length > 0"
            title="确定要删除这个计划吗？"
            ok-text="确定"
            cancel-text="取消"
            @confirm="handleRemovePlan(activePlanId)"
          >
            <a-button danger size="large" :disabled="!activePlanId">
              <template #icon>
                <DeleteOutlined />
              </template>
              删除当前计划
            </a-button>
          </a-popconfirm>

          <a-button size="large" @click="handleRefresh">
            <template #icon>
              <ReloadOutlined />
            </template>
            刷新
          </a-button>
        </a-space>
      </div>
    </div>

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
      <!-- 计划选择卡片 -->
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
                @click="onPlanChange(plan.id)"
                class="plan-button"
              >
                {{ plan.name }}
              </a-button>
            </a-space>
          </div>
        </div>
      </a-card>

      <!-- 计划配置卡片 -->
      <a-card class="plan-config-card" :bordered="false">
        <template #title>
          <div class="plan-title-container">
            <div v-if="!isEditingPlanName" class="plan-title-display">
              <span class="plan-title-text">{{ currentPlanName || '计划配置' }}</span>
              <a-button type="text" size="small" @click="startEditPlanName" class="plan-edit-btn">
                <template #icon>
                  <EditOutlined />
                </template>
              </a-button>
            </div>
            <div v-else class="plan-title-edit">
              <a-input
                v-model:value="currentPlanName"
                placeholder="请输入计划名称"
                size="small"
                class="plan-title-input"
                @blur="finishEditPlanName"
                @pressEnter="finishEditPlanName"
                :maxlength="50"
                ref="planNameInputRef"
              />
            </div>
          </div>
        </template>
        <template #extra>
          <a-space>
            <span class="mode-label">执行模式：</span>
            <a-segmented
              v-model:value="currentMode"
              @change="onModeChange"
              :options="[
                { label: '全局模式', value: 'ALL' },
                { label: '周计划模式', value: 'Weekly' },
              ]"
            />
          </a-space>
        </template>

        <!-- 配置表格 -->
        <div class="config-table-container">
          <a-table
            :columns="dynamicTableColumns"
            :data-source="tableData"
            :pagination="false"
            class="config-table"
            size="middle"
            :bordered="true"
            :scroll="{ x: false }"
          >
            <template #bodyCell="{ column, record, index }">
              <template v-if="column.key === 'taskName'">
                <div class="task-name-cell">
                  <a-tag :color="getTaskTagColor(record.taskName)" class="task-tag">
                    {{ record.taskName }}
                  </a-tag>
                </div>
              </template>
              <template v-else-if="record.taskName === '吃理智药'">
                <a-input-number
                  v-model:value="record[column.key]"
                  size="small"
                  :min="0"
                  :max="999"
                  :placeholder="getPlaceholder(column.key, record.taskName)"
                  class="config-input-number"
                  :controls="false"
                />
              </template>
              <template v-else>
                <a-select
                  v-model:value="record[column.key]"
                  size="small"
                  :options="getSelectOptions(column.key, record.taskName)"
                  :placeholder="getPlaceholder(column.key, record.taskName)"
                  class="config-select"
                  allow-clear
                  :show-search="true"
                  :filter-option="filterOption"
                />
              </template>
            </template>
          </a-table>
        </div>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, ReloadOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons-vue'
import { usePlanApi } from '../composables/usePlanApi'

// API 相关
const { getPlans, createPlan, updatePlan, deletePlan } = usePlanApi()

// 计划列表和当前选中的计划
const planList = ref<Array<{ id: string; name: string }>>([])
const activePlanId = ref<string>('')
const currentPlanData = ref<Record<string, any> | null>(null)

// 当前计划的名称和模式
const currentPlanName = ref<string>('')
const currentMode = ref<'ALL' | 'Weekly'>('ALL')
// 计划名称编辑状态
const isEditingPlanName = ref<boolean>(false)
// 显示名称提示
const showNameTip = ref<boolean>(false)

const loading = ref(true)

// 表格列配置（全局和周计划模式都使用相同的表格结构）
const dynamicTableColumns = computed(() => {
  return tableColumns.value
})

// 表格列配置
const tableColumns = ref([
  {
    title: '配置项',
    dataIndex: 'taskName',
    key: 'taskName',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  {
    title: '全局',
    dataIndex: 'ALL',
    key: 'ALL',
    width: 120,
    align: 'center',
  },
  {
    title: '周一',
    dataIndex: 'Monday',
    key: 'Monday',
    width: 120,
    align: 'center',
  },
  {
    title: '周二',
    dataIndex: 'Tuesday',
    key: 'Tuesday',
    width: 120,
    align: 'center',
  },
  {
    title: '周三',
    dataIndex: 'Wednesday',
    key: 'Wednesday',
    width: 120,
    align: 'center',
  },
  {
    title: '周四',
    dataIndex: 'Thursday',
    key: 'Thursday',
    width: 120,
    align: 'center',
  },
  {
    title: '周五',
    dataIndex: 'Friday',
    key: 'Friday',
    width: 120,
    align: 'center',
  },
  {
    title: '周六',
    dataIndex: 'Saturday',
    key: 'Saturday',
    width: 120,
    align: 'center',
  },
  {
    title: '周日',
    dataIndex: 'Sunday',
    key: 'Sunday',
    width: 120,
    align: 'center',
  },
])

// 表格数据
const tableData = ref([
  {
    key: 'MedicineNumb',
    taskName: '吃理智药',
    ALL: 0,
    Monday: 0,
    Tuesday: 0,
    Wednesday: 0,
    Thursday: 0,
    Friday: 0,
    Saturday: 0,
    Sunday: 0,
  },
  {
    key: 'SeriesNumb',
    taskName: '连战次数',
    ALL: '0',
    Monday: '0',
    Tuesday: '0',
    Wednesday: '0',
    Thursday: '0',
    Friday: '0',
    Saturday: '0',
    Sunday: '0',
  },
  {
    key: 'Stage',
    taskName: '关卡选择',
    ALL: '-',
    Monday: '-',
    Tuesday: '-',
    Wednesday: '-',
    Thursday: '-',
    Friday: '-',
    Saturday: '-',
    Sunday: '-',
  },
  {
    key: 'Stage_1',
    taskName: '备选-1',
    ALL: '-',
    Monday: '-',
    Tuesday: '-',
    Wednesday: '-',
    Thursday: '-',
    Friday: '-',
    Saturday: '-',
    Sunday: '-',
  },
  {
    key: 'Stage_2',
    taskName: '备选-2',
    ALL: '-',
    Monday: '-',
    Tuesday: '-',
    Wednesday: '-',
    Thursday: '-',
    Friday: '-',
    Saturday: '-',
    Sunday: '-',
  },
  {
    key: 'Stage_3',
    taskName: '备选-3',
    ALL: '-',
    Monday: '-',
    Tuesday: '-',
    Wednesday: '-',
    Thursday: '-',
    Friday: '-',
    Saturday: '-',
    Sunday: '-',
  },
  {
    key: 'Stage_Remain',
    taskName: '剩余理智',
    ALL: '-',
    Monday: '-',
    Tuesday: '-',
    Wednesday: '-',
    Thursday: '-',
    Friday: '-',
    Saturday: '-',
    Sunday: '-',
  },
])

// 关卡数据配置
const STAGE_DAILY_INFO = [
  { value: '-', text: '当前/上次', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: '1-7', text: '1-7', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: 'R8-11', text: 'R8-11', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: '12-17-HARD', text: '12-17-HARD', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: 'CE-6', text: '龙门币-6/5', days: [2, 4, 6, 7] },
  { value: 'AP-5', text: '红票-5', days: [1, 4, 6, 7] },
  { value: 'CA-5', text: '技能-5', days: [2, 3, 5, 7] },
  { value: 'LS-6', text: '经验-6/5', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: 'SK-5', text: '碳-5', days: [1, 3, 5, 6] },
  { value: 'PR-A-1', text: '奶/盾芯片', days: [1, 4, 5, 7] },
  { value: 'PR-A-2', text: '奶/盾芯片组', days: [1, 4, 5, 7] },
  { value: 'PR-B-1', text: '术/狙芯片', days: [1, 2, 5, 6] },
  { value: 'PR-B-2', text: '术/狙芯片组', days: [1, 2, 5, 6] },
  { value: 'PR-C-1', text: '先/辅芯片', days: [3, 4, 6, 7] },
  { value: 'PR-C-2', text: '先/辅芯片组', days: [3, 4, 6, 7] },
  { value: 'PR-D-1', text: '近/特芯片', days: [2, 3, 6, 7] },
  { value: 'PR-D-2', text: '近/特芯片组', days: [2, 3, 6, 7] },
]

// 获取星期对应的数字
const getDayNumber = (columnKey: string) => {
  const dayMap: Record<string, number> = {
    ALL: 0, // 全局显示所有选项
    Monday: 1,
    Tuesday: 2,
    Wednesday: 3,
    Thursday: 4,
    Friday: 5,
    Saturday: 6,
    Sunday: 7,
  }
  return dayMap[columnKey] || 0
}

// 获取选择器选项
const getSelectOptions = (columnKey: string, taskName: string) => {
  switch (taskName) {
    case '连战次数':
      return [
        { label: '不选择', value: '0' },
        { label: '1', value: '1' },
        { label: '2', value: '2' },
        { label: '3', value: '3' },
        { label: '4', value: '4' },
        { label: '5', value: '5' },
        { label: '6', value: '6' },
        { label: 'AUTO', value: '-1' },
      ]
    case '关卡选择':
    case '备选-1':
    case '备选-2':
    case '备选-3':
    case '剩余理智': {
      const dayNumber = getDayNumber(columnKey)

      // 如果是全局列，显示所有选项
      if (dayNumber === 0) {
        return STAGE_DAILY_INFO.map(stage => ({
          label: stage.text,
          value: stage.value,
        }))
      }

      // 根据星期过滤可用的关卡
      return STAGE_DAILY_INFO.filter(stage => stage.days.includes(dayNumber)).map(stage => ({
        label: stage.text,
        value: stage.value,
      }))
    }
    default:
      return []
  }
}

// 获取占位符
const getPlaceholder = (columnKey: string, taskName: string) => {
  switch (taskName) {
    case '吃理智药':
      return '输入数量'
    case '连战次数':
      return '选择次数'
    case '关卡选择':
    case '备选-1':
    case '备选-2':
    case '备选-3':
      return '1-7'
    case '剩余理智':
      return '1-8'
    default:
      return '请选择'
  }
}

// 模式切换处理
const onModeChange = () => {
  // 模式切换时只更新本地状态，不自动保存
  // 用户需要手动点击保存按钮
}

// 计划名称编辑失焦处理
const onPlanNameBlur = () => {
  // 当用户编辑完计划名称后，更新按钮显示的名称
  if (activePlanId.value) {
    const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
    if (currentPlan) {
      currentPlan.name = currentPlanName.value || `计划 ${planList.value.indexOf(currentPlan) + 1}`
    }
  }
}

// 开始编辑计划名称
const startEditPlanName = () => {
  isEditingPlanName.value = true
  // 使用 nextTick 确保 DOM 更新后再获取焦点
  setTimeout(() => {
    const input = document.querySelector('.plan-title-input input') as HTMLInputElement
    if (input) {
      input.focus()
      input.select()
    }
  }, 100)
}

// 完成编辑计划名称
const finishEditPlanName = () => {
  isEditingPlanName.value = false
  onPlanNameBlur()
}

// 手动保存处理
const handleSave = async () => {
  if (!activePlanId.value) {
    message.warning('请先选择一个计划')
    return
  }
  try {
    await savePlanData()
    // message.success('保存成功')
  } catch (error) {
    message.error('保存失败')
  }
}

// 添加计划
const handleAddPlan = async () => {
  try {
    const response = await createPlan('MaaPlan')
    const defaultName = '新 MAA 计划表'
    const newPlan = {
      id: response.planId,
      name: defaultName,
    }
    planList.value.push(newPlan)
    activePlanId.value = newPlan.id

    // 设置默认名称到输入框中
    currentPlanName.value = defaultName

    await loadPlanData(newPlan.id)

    // 显示名称修改提示
    message.info('已创建新的MAA计划表，建议您修改为更有意义的名称', 3)
  } catch (error) {
    console.error('添加计划失败:', error)
  }
}

// 删除计划
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

// 计划切换
const onPlanChange = async (planId: string) => {
  // 立即更新activePlanId以确保按钮高亮切换
  activePlanId.value = planId
  await loadPlanData(planId)
}

// 加载计划数据
const loadPlanData = async (planId: string) => {
  try {
    const response = await getPlans(planId)
    currentPlanData.value = response.data

    // 根据API响应数据更新表格数据
    if (response.data && response.data[planId]) {
      const planData = response.data[planId]

      // 更新计划名称和模式
      if (planData.Info) {
        // 如果API返回的名称为空，并且当前输入框也为空，则使用默认名称
        const apiName = planData.Info.Name || ''
        if (!apiName && !currentPlanName.value) {
          // 找到当前计划在列表中的位置，使用默认名称
          const currentPlan = planList.value.find(plan => plan.id === planId)
          if (currentPlan) {
            currentPlanName.value = currentPlan.name
          }
        } else if (apiName) {
          // 如果API有名称，使用API的名称
          currentPlanName.value = apiName
        }
        // 如果API名称为空但当前输入框有值，保持当前值不变

        currentMode.value = planData.Info.Mode || 'ALL'
      }

      // 更新表格数据
      tableData.value.forEach(row => {
        const fieldKey = row.key

        // 更新每个时间段的数据
        const timeKeys = [
          'ALL',
          'Monday',
          'Tuesday',
          'Wednesday',
          'Thursday',
          'Friday',
          'Saturday',
          'Sunday',
        ]
        timeKeys.forEach(timeKey => {
          if (planData[timeKey] && planData[timeKey][fieldKey] !== undefined) {
            row[timeKey] = planData[timeKey][fieldKey]
          }
        })
      })
    }
  } catch (error) {
    console.error('加载计划数据失败:', error)
  }
}

// 初始化
const initPlans = async () => {
  try {
    const response = await getPlans()
    if (response.index && response.index.length > 0) {
      planList.value = response.index.map((item: any, index: number) => {
        // API响应格式: {"uid": "xxx", "type": "MaaPlanConfig"}
        const planId = item.uid
        const planName = response.data[planId]?.Info?.Name || `计划 ${index + 1}`
        return {
          id: planId,
          name: planName,
        }
      })
      activePlanId.value = planList.value[0].id
      await loadPlanData(activePlanId.value)
    } else {
      // 如果没有计划，显示空状态而不是自动创建
      currentPlanData.value = null
    }
  } catch (error) {
    console.error('初始化计划失败:', error)
    // 显示空状态
    currentPlanData.value = null
  } finally {
    loading.value = false
  }
}

// 保存计划数据
const savePlanData = async () => {
  if (!activePlanId.value) return

  try {
    // 构建符合API要求的数据结构
    const planData: Record<string, Record<string, any>> = {}

    // 为每个时间段构建数据
    const timeKeys = [
      'ALL',
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
      'Friday',
      'Saturday',
      'Sunday',
    ]

    timeKeys.forEach(timeKey => {
      planData[timeKey] = {}
      tableData.value.forEach(row => {
        planData[timeKey][row.key] = row[timeKey]
      })
    })

    // 添加Info信息
    planData['Info'] = {
      Mode: currentMode.value,
      Name: currentPlanName.value,
    }

    await updatePlan(activePlanId.value, planData)
  } catch (error) {
    console.error('保存计划数据失败:', error)
    throw error
  }
}

// 刷新计划列表
const handleRefresh = async () => {
  loading.value = true
  await initPlans()
  loading.value = false
  // message.success('刷新成功')
}

// 自动保存功能
watch(
  () => [currentPlanName.value, currentMode.value, tableData.value],
  async () => {
    // 使用nextTick确保DOM更新后再保存
    await nextTick()
    handleSave()
  },
  { deep: true }
)

// 移除自动保存功能，改为手动保存
// 用户需要点击悬浮按钮才能保存数据

onMounted(() => {
  initPlans()
})

// 新增方法：获取任务标签颜色
const getTaskTagColor = (taskName: string) => {
  const colorMap: Record<string, string> = {
    吃理智药: 'blue',
    连战次数: 'green',
    关卡选择: 'orange',
    '备选-1': 'purple',
    '备选-2': 'purple',
    '备选-3': 'purple',
    剩余理智: 'cyan',
  }
  return colorMap[taskName] || 'default'
}

// 新增方法：选择器过滤
const filterOption = (input: string, option: any) => {
  return option.label.toLowerCase().includes(input.toLowerCase())
}
</script>

<style scoped>
.plans-container {
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
  padding: 24px;
}

.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.plans-main {
  max-width: 1400px;
  margin: 0 auto;
}

/* 页面头部 */
.plans-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  padding: 0 4px;
}

.header-left {
  flex: 1;
}

.page-title {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.page-description {
  margin: 0;
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  line-height: 1.5;
}

.header-actions {
  flex-shrink: 0;
}

/* 空状态 */
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
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

/* 计划内容 */
.plans-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 计划选择卡片 */
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

/* 计划按钮组 */
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
}

/* 计划配置卡片 */
.plan-config-card {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  min-height: 600px;
}

.mode-label {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  font-weight: 500;
}

/* 计划名称编辑 */
.plan-title-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.plan-title-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-title-text {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.plan-edit-btn {
  color: var(--ant-color-primary);
  padding: 0;
}

/* 计划名称输入框 */
.plan-title-input {
  flex: 1;
  max-width: 400px;
  border-radius: 8px;
  transition: all 0.2s ease;
}

/* 配置表格 */
.config-table-container {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--ant-color-border-secondary);
}

.config-table {
  margin: 0;
}

/* 任务名称单元格 */
.task-name-cell {
  display: flex;
  justify-content: center;
  align-items: center;
}

.task-tag {
  margin: 0;
  padding: 4px 12px;
  border-radius: 6px;
  font-weight: 500;
  font-size: 13px;
}

/* 配置输入组件 */
.config-select {
  width: 100%;
  min-width: 100px;
}

.config-input-number {
  width: 100%;
  min-width: 100px;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .plans-container {
    padding: 16px;
  }

  .plans-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .page-title {
    font-size: 28px;
  }

  .config-table-container {
    overflow-x: auto;
  }
}

@media (max-width: 768px) {
  .plans-container {
    padding: 12px;
  }

  .page-title {
    font-size: 24px;
  }

  .page-description {
    font-size: 14px;
  }

  .plan-title-input {
    max-width: 100%;
  }

  .header-actions {
    width: 100%;
    display: flex;
    justify-content: center;
  }
}

/* 深度样式使用全局CSS变量 */
.plan-selector-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 16px 24px;
}

.plan-config-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 16px 24px;
}

.plan-config-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.plan-title-container :deep(.ant-form-item-label) {
  font-weight: 600;
  color: var(--ant-color-text);
}

.plan-title-input :deep(.ant-input) {
  font-size: 16px;
  font-weight: 500;
}

.plan-title-input :deep(.ant-input:focus) {
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg-hover);
}

.config-table :deep(.ant-table-thead > tr > th) {
  background: var(--ant-color-bg-container-disabled);
  border-bottom: 2px solid var(--ant-color-border);
  font-weight: 600;
  color: var(--ant-color-text);
  text-align: center;
  padding: 16px 12px;
  font-size: 14px;
}

.config-table :deep(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  text-align: center;
  padding: 12px 8px;
  vertical-align: middle;
}

.config-table :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--ant-color-bg-container-disabled);
}

.config-select :deep(.ant-select-selector) {
  border-radius: 6px;
  transition: all 0.2s ease;
}

.config-select :deep(.ant-select-selector:hover) {
  border-color: var(--ant-color-primary-hover);
}

.config-select :deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg-hover);
}

.config-input-number :deep(.ant-input-number) {
  border-radius: 6px;
  width: 100%;
}

.config-input-number :deep(.ant-input-number-focused) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg-hover);
}

.plan-tabs :deep(.ant-tabs-tab) {
  padding: 12px 20px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 8px 8px 0 0;
  transition: all 0.2s ease;
}

.plan-tabs :deep(.ant-tabs-tab-active) {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
}

:deep(.ant-float-btn-group .ant-float-btn-group-circle-wrapper) {
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
}
</style>
