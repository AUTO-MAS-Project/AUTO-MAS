<template>
  <div v-if="loading" class="loading-box">
    <a-spin tip="加载中，请稍候..." size="large" />
  </div>
  <!-- 有计划时显示 -->
  <div v-else class="plans-content">
    <!-- 计划头部 -->
    <div class="plans-header">
      <div class="header-title">
        <h1>计划管理</h1>
      </div>
      <a-space size="middle">
        <a-button type="primary" size="large" @click="handleAddPlan">
          <template #icon>
            <PlusOutlined />
          </template>
          新建计划
        </a-button>
        <a-button size="large" @click="handleRefresh">
          <template #icon>
            <ReloadOutlined />
          </template>
          刷新
        </a-button>
      </a-space>
    </div>

    <!-- 如果没有计划，显示占位符 -->
    <div v-if="!planList.length || !currentPlanData" class="placeholder-container">
      <div class="placeholder-content">
        <h2>当前没有计划</h2>
        <p>您还没有创建任何计划，点击下方按钮来创建您的第一个计划</p>
        <a-button type="primary" size="large" @click="handleAddPlan">
          <template #icon>
            <PlusOutlined />
          </template>
          新建计划
        </a-button>
      </div>
    </div>



    <div class="plan-content" v-else v-if="currentPlanData">
      <!-- 计划选择器 -->
      <div class="plan-selector">
        <a-tabs
          v-model:activeKey="activePlanId"
          type="editable-card"
          @edit="onTabEdit"
          @change="onPlanChange"
          class="plan-tabs"
        >
          <a-tab-pane
            v-for="plan in planList"
            :key="plan.id"
            :tab="plan.name"
            :closable="planList.length > 0"
          />
        </a-tabs>
      </div>
      <!-- MAA计划配置 -->
      <div class="maa-config-section">
        <div class="section-header">
          <div class="section-title">
            <div class="plan-name-editor">
              <a-input
                v-model:value="currentPlanName"
                placeholder="请输入计划名称"
                size="large"
                class="plan-name-input"
                @blur="onPlanNameBlur"
                @pressEnter="onPlanNameBlur"
              />
            </div>
          </div>
          <div class="section-controls">
            <a-space>
              <span class="mode-label">模式：</span>
              <a-radio-group v-model:value="currentMode" @change="onModeChange" size="default">
                <a-radio-button value="ALL">全局</a-radio-button>
                <a-radio-button value="Weekly">周计划</a-radio-button>
              </a-radio-group>
            </a-space>
          </div>
        </div>

        <!-- 使用 Ant Design 表格组件 -->
        <a-table
          :columns="dynamicTableColumns"
          :data-source="tableData"
          :pagination="false"
          :scroll="{ x: 1000 }"
          class="plan-table"
          size="middle"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'taskName'">
              <div class="task-name">
                {{ record.taskName }}
              </div>
            </template>
            <template v-else-if="record.taskName === '吃理智药'">
              <a-input-number
                v-model:value="record[column.key]"
                size="small"
                :min="0"
                :max="999"
                :placeholder="getPlaceholder(column.key, record.taskName)"
                class="config-input"
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
              />
            </template>
          </template>
        </a-table>
      </div>
    </div>
  </div>

  <!-- 悬浮保存按钮 -->
  <a-float-button
    type="primary"
    @click="handleSave"
    class="float-button"
    :style="{ right: '24px' }"
  >
    <template #icon>
      <SaveOutlined />
    </template>
  </a-float-button>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons-vue'
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
        { label: '0', value: '0' },
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
  // 当用户编辑完计划名称后，更新标签页显示的名称
  if (activePlanId.value) {
    const currentPlan = planList.value.find(plan => plan.id === activePlanId.value)
    if (currentPlan) {
      currentPlan.name = currentPlanName.value || `计划 ${planList.value.indexOf(currentPlan) + 1}`
    }
  }
}

// 手动保存处理
const handleSave = async () => {
  if (!activePlanId.value) {
    message.warning('请先选择一个计划')
    return
  }
  try {
    await savePlanData()
    message.success('保存成功')
  } catch (error) {
    message.error('保存失败')
  }
}

// 标签页编辑处理
const onTabEdit = async (targetKey: string | MouseEvent, action: 'add' | 'remove') => {
  if (action === 'add') {
    await handleAddPlan()
  } else if (action === 'remove' && typeof targetKey === 'string') {
    await handleRemovePlan(targetKey)
  }
}

// 添加计划
const handleAddPlan = async () => {
  try {
    const response = await createPlan('MaaPlan')
    const defaultName = `计划 ${planList.value.length + 1}`
    const newPlan = {
      id: response.planId,
      name: defaultName,
    }
    planList.value.push(newPlan)
    activePlanId.value = newPlan.id

    // 设置默认名称到输入框中
    currentPlanName.value = defaultName

    await loadPlanData(newPlan.id)
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
        }
      }
    }
  } catch (error) {
    console.error('删除计划失败:', error)
  }
}

// 计划切换
const onPlanChange = async (planId: string) => {
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

// 移除自动保存功能，改为手动保存
// 用户需要点击悬浮按钮才能保存数据

onMounted(() => {
  initPlans()
})
</script>

<style scoped>
/* 空状态样式 */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-content {
  text-align: center;
  padding: 48px;
  background: var(--ant-color-bg-container);
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  border: 1px solid var(--ant-color-border-secondary);
}

.empty-icon {
  font-size: 64px;
  color: var(--ant-color-text-tertiary);
  margin-bottom: 24px;
}

.empty-content h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0 0 8px 0;
}

.empty-content p {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 32px 0;
}

/* 计划内容区域 */
.plans-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--ant-color-bg-container);
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

/* 计划头部样式 */
.plans-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 32px;
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border-secondary);
  margin-bottom: 5px;
}

.header-title h1 {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* 计划选择器 */
.plan-selector {
  padding: 0 32px;
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

/* 计划内容 */
.plan-content {
  flex: 1;
  padding: 24px 32px;
  overflow: auto;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.section-title h3 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
}

.section-controls {
  display: flex;
  align-items: center;
}

.mode-label {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  font-weight: 500;
}

/* 计划名称编辑器样式 */
.plan-name-editor {
  display: flex;
  align-items: center;
}

.plan-name-input {
  max-width: 300px;
  font-size: 18px;
  font-weight: 600;
}

.plan-name-input :deep(.ant-input) {
  border: 1px solid transparent;
  background: transparent;
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.3s ease;
}

.plan-name-input :deep(.ant-input:hover) {
  border-color: var(--ant-color-border);
}

.plan-name-input :deep(.ant-input:focus) {
  border-color: var(--ant-color-primary);

  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

/* 表格样式 */
.plan-table {
  background: var(--ant-color-bg-container);
}

.plan-table :deep(.ant-table-thead > tr > th) {
  border-bottom: 2px solid var(--ant-color-border);
  font-weight: 600;
  color: var(--ant-color-text);
  text-align: center;
}

.plan-table :deep(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  text-align: center;
  padding: 12px 8px;
}

.task-name {
  font-weight: 600;
  color: var(--ant-color-text);
  text-align: center;
}

.config-select {
  width: 100%;
  min-width: 100px;
}

.config-select :deep(.ant-select-selector) {
  border-radius: 6px;
  border: 1px solid var(--ant-color-border);
}

.config-select :deep(.ant-select-selector:hover) {
  border-color: var(--ant-color-primary-hover);
}

.config-select :deep(.ant-select-focused .ant-select-selector) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

/* 输入框样式 */
.config-input {
  width: 100%;
  min-width: 100px;
}

.config-input :deep(.ant-input-number-focused) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .maa-config-section {
    border-color: var(--ant-color-border-secondary);
    border-radius: 16px;
  }

  .section-header {
    border-color: var(--ant-color-border-secondary);
    border-radius: 16px;
  }
}

.float-button {
  width: 60px;
  height: 60px;
}

.empty-content-fancy {
  transition:
    box-shadow 0.3s,
    transform 0.2s;
  border: none;
  border-radius: 24px;
}

.empty-icon {
  font-size: 80px;
  margin-bottom: 32px;
  border-radius: 50%;
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
  margin-right: auto;
}

.empty-content-fancy h3 {
  font-size: 26px;
  font-weight: 700;
  margin: 0 0 12px 0;
  letter-spacing: 1px;
}

.empty-content-fancy p {
  font-size: 16px;
  border-radius: 8px;
  padding: 8px 16px;
  margin: 0 0 12px 0;
  display: inline-block;
}

.loading-box {
  min-height: 400px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.placeholder-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 400px;
}

.placeholder-content {
  text-align: center;
  max-width: 500px;
}

.placeholder-content h2 {
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 16px;
}

.placeholder-content p {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  margin-bottom: 24px;
  line-height: 1.5;
}

.empty-content-fancy h2 {
  font-size: 26px;
  font-weight: 700;
  margin: 0 0 12px 0;
  letter-spacing: 1px;
  color: var(--ant-color-text);
}
</style>
