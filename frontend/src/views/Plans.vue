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
          <a-button type="primary" size="large" @click="handleAddPlan">
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
            <span class="view-label">视图：</span>
            <a-segmented
              v-model:value="viewMode"
              :options="[
                { label: '配置视图', value: 'config' },
                { label: '简化视图', value: 'simple' },
              ]"
            />
          </a-space>
        </template>

        <!-- 配置表格 -->
        <div class="config-table-container">
          <!-- 配置视图 -->
          <div v-if="viewMode === 'config'" class="config-table-wrapper">
            <a-table
              :columns="dynamicTableColumns"
              :data-source="tableData"
              :pagination="false"
              :class="['config-table', `mode-${currentMode}`]"
              size="middle"
              :bordered="true"
              :scroll="{ x: 'max-content' }"
              :row-class-name="(record: TableRow) => `task-row-${record.key}`"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'taskName'">
                  {{ record.taskName }}
                </template>
                <template v-else-if="record.taskName === '吃理智药'">
                  <a-input-number
                    v-model:value="record[column.key]"
                    size="small"
                    :min="0"
                    :max="999"
                    :placeholder="getPlaceholder(record.taskName)"
                    class="config-input-number"
                    :controls="false"
                    :disabled="isColumnDisabled(column.key)"
                  />
                </template>
                <template
                  v-else-if="
                    ['关卡选择', '备选关卡-1', '备选关卡-2', '备选关卡-3', '剩余理智关卡'].includes(
                      record.taskName
                    )
                  "
                >
                  <a-select
                    v-model:value="record[column.key]"
                    size="small"
                    :placeholder="getPlaceholder(record.taskName)"
                    :class="[
                      'config-select',
                      { 'custom-stage-selected': isCustomStage(record[column.key], column.key) },
                    ]"
                    allow-clear
                    :disabled="isColumnDisabled(column.key)"
                  >
                    <template #dropdownRender="{ menuNode: menu }">
                      <v-nodes :vnodes="menu" />
                      <a-divider style="margin: 4px 0" />
                      <a-space style="padding: 4px 8px" size="small">
                        <a-input
                          v-model:value="customStageNames[`${record.key}_${column.key}`]"
                          placeholder="自定义"
                          style="flex: 1"
                          size="small"
                          @keyup.enter="addCustomStage(record.key, column.key)"
                        />
                        <a-button
                          type="text"
                          size="small"
                          @click="addCustomStage(record.key, column.key)"
                        >
                          <template #icon>
                            <PlusOutlined />
                          </template>
                        </a-button>
                      </a-space>
                    </template>
                    <a-select-option
                      v-for="option in getSelectOptions(
                        column.key,
                        record.taskName,
                        record[column.key]
                      )"
                      :key="option.value"
                      :value="option.value"
                    >
                      <template v-if="option.label && option.label.includes('|')">
                        <span>{{ option.label.split('|')[0] }}</span>
                        <a-tag color="green" size="small" style="margin-left: 8px">
                          {{ option.label.split('|')[1] }}
                        </a-tag>
                      </template>
                      <template v-else>
                        <span
                          :style="
                            isCustomStage(option.value, column.key)
                              ? { color: 'var(--ant-color-primary)', fontWeight: '500' }
                              : {}
                          "
                        >
                          {{ option.label }}
                        </span>
                      </template>
                    </a-select-option>
                  </a-select>
                </template>
                <template v-else>
                  <a-select
                    v-model:value="record[column.key]"
                    size="small"
                    :options="getSelectOptions(column.key, record.taskName, record[column.key])"
                    :placeholder="getPlaceholder(record.taskName)"
                    class="config-select"
                    allow-clear
                    :disabled="isColumnDisabled(column.key)"
                  />
                </template>
              </template>
            </a-table>
          </div>

          <div v-else class="simple-table-wrapper">
            <a-table
              :columns="dynamicSimpleViewColumns"
              :data-source="simpleViewData"
              :pagination="false"
              class="simple-table"
              size="small"
              :bordered="true"
              :scroll="{ x: 'max-content' }"
            >
              <template #bodyCell="{ column, record }">
                <!-- 全选列 -->
                <template v-if="column.key === 'globalControl'">
                  <a-space>
                    <a-tooltip title="开/关所有可用关卡" placement="left">
                      <a-button
                        ghost
                        size="small"
                        type="primary"
                        @click="enableAllStages(record.key)"
                        >开
                      </a-button>
                    </a-tooltip>

                    <a-button size="small" danger @click="disableAllStages(record.key)">
                      关
                    </a-button>
                  </a-space>
                </template>

                <template v-else-if="column.key === 'taskName'">
                  <div class="task-name-cell">
                    <a-tag :color="getSimpleTaskTagColor(record.taskName)" class="task-tag">
                      {{ record.taskName }}
                    </a-tag>
                  </div>
                </template>
                <template v-else>
                  <!-- 只在关卡可用时显示开关 -->
                  <div v-if="isStageAvailable(record.key, column.key)">
                    <a-switch
                      :checked="isStageEnabled(record.key, column.key)"
                      @change="(checked: boolean) => toggleStage(record.key, column.key, checked)"
                    />
                  </div>
                </template>
              </template>
            </a-table>
          </div>
        </div>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, nextTick, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { usePlanApi } from '../composables/usePlanApi'
import { useRoute } from 'vue-router' // 新增

interface TableRow {
  key: string
  taskName: string
  ALL: string | number
  Monday: string | number
  Tuesday: string | number
  Wednesday: string | number
  Thursday: string | number
  Friday: string | number
  Saturday: string | number
  Sunday: string | number

  [key: string]: string | number // 保留动态属性支持
}

interface PlanData {
  [key: string]: any

  Info?: {
    Mode: 'ALL' | 'Weekly'
    Name: string
  }
}

// API 相关
const { getPlans, createPlan, updatePlan, deletePlan } = usePlanApi()

// 计划列表和当前选中的计划
const planList = ref<Array<{ id: string; name: string }>>([])
const activePlanId = ref<string>('')

const currentPlanData = ref<PlanData | null>(null)

// 当前计划的名称和模式、视图
const currentPlanName = ref<string>('')
const currentMode = ref<'ALL' | 'Weekly'>('ALL')
const viewMode = ref<'config' | 'simple'>('config')

// 计划名称编辑状态
const isEditingPlanName = ref<boolean>(false)

const loading = ref(true)

// VNodes 组件，用于渲染下拉菜单内容
const VNodes = defineComponent({
  props: { vnodes: { type: Object, required: true } },
  setup(props) {
    return () => props.vnodes as any
  },
})

// 自定义关卡相关变量
const customStageNames = ref<Record<string, string>>({})

// 关卡选项，包含自定义关卡
const stageOptions = computed(() => {
  const baseOptions = STAGE_DAILY_INFO.map(stage => ({
    label: stage.text,
    value: stage.value,
    isCustom: false,
  }))

  // 添加自定义关卡
  const customOptions = Object.keys(customStageNames.value).map(key => ({
    label: customStageNames.value[key],
    value: key,
    isCustom: true,
  }))

  return [...baseOptions, ...customOptions]
})

// 添加自定义关卡的函数
const addCustomStage = (rowKey: string, columnKey: string) => {
  const inputName = `${rowKey}_${columnKey}`
  const customName = customStageNames.value[inputName]

  if (!customName || !customName.trim()) {
    message.warning('请输入关卡名称')
    return
  }

  // 验证关卡名称格式
  const stagePattern = /^[A-Za-z0-9\-_]+$/
  if (!stagePattern.test(customName.trim())) {
    message.warning('关卡名称只能包含字母、数字、短横线和下划线')
    return
  }

  // 检查是否已存在
  const existingOption = stageOptions.value.find(option => option.value === customName.trim())
  if (existingOption) {
    message.warning('该关卡已存在')
    return
  }

  // 添加到选项中
  customStageNames.value[customName.trim()] = customName.trim()

  // 设置为当前值
  const targetRow = tableData.value.find(row => row.key === rowKey)
  if (targetRow) {
    ;(targetRow as any)[columnKey] = customName.trim()
  }

  // 清空输入框
  customStageNames.value[inputName] = ''

  message.success('关卡添加成功')
}

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
    className: 'task-name-td',
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
    taskName: '备选关卡-1',
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
    taskName: '备选关卡-2',
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
    taskName: '备选关卡-3',
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
    taskName: '剩余理智关卡',
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

// 简化视图专用列配置
const dynamicSimpleViewColumns = computed(() => {
  return [
    {
      title: '全局控制',
      key: 'globalControl',
      width: 75,
      fixed: 'left',
      align: 'center',
    },
    {
      title: '关卡', // 修改列名为"关卡"
      dataIndex: 'taskName',
      key: 'taskName',
      width: 120,
      fixed: 'left',
      align: 'center',
    },
    ...tableColumns.value.filter(col => col.key !== 'taskName' && col.key !== 'globalControl'),
  ]
})

// 关卡数据配置
const STAGE_DAILY_INFO = [
  { value: '-', text: '当前/上次', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: '1-7', text: '1-7', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: 'R8-11', text: 'R8-11', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: '12-17-HARD', text: '12-17-HARD', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: 'LS-6', text: '经验-6/5', days: [1, 2, 3, 4, 5, 6, 7] },
  { value: 'CE-6', text: '龙门币-6/5', days: [2, 4, 6, 7] },
  { value: 'AP-5', text: '红票-5', days: [1, 4, 6, 7] },
  { value: 'CA-5', text: '技能-5', days: [2, 3, 5, 7] },
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

// 判断值是否为自定义关卡
const isCustomStage = (value: string, columnKey: string) => {
  if (!value || value === '-') return false

  const dayNumber = getDayNumber(columnKey)

  // 获取当前列可用的预定义关卡值
  let availableStages = []
  if (dayNumber === 0) {
    // 全局列显示所有关卡
    availableStages = STAGE_DAILY_INFO.map(stage => stage.value)
  } else {
    // 根据星期过滤可用的关卡
    availableStages = STAGE_DAILY_INFO.filter(stage => stage.days.includes(dayNumber)).map(
      stage => stage.value
    )
  }

  // 如果值不在预定义列表中，则为自定义
  return !availableStages.includes(value)
}

// 获取选择器选项
const getSelectOptions = (columnKey: string, taskName: string, currentValue?: string) => {
  switch (taskName) {
    case '连战次数':
      return [
        { label: 'AUTO', value: '0' },
        { label: '1', value: '1' },
        { label: '2', value: '2' },
        { label: '3', value: '3' },
        { label: '4', value: '4' },
        { label: '5', value: '5' },
        { label: '6', value: '6' },
        { label: '不切换', value: '-1' },
      ]
    case '关卡选择':
    case '备选关卡-1':
    case '备选关卡-2':
    case '备选关卡-3':
    case '剩余理智关卡': {
      const dayNumber = getDayNumber(columnKey)

      // 基础关卡选项
      let baseOptions = []
      if (dayNumber === 0) {
        // 如果是全局列，显示所有选项
        baseOptions = STAGE_DAILY_INFO.map(stage => ({
          label: taskName === '剩余理智关卡' && stage.value === '-' ? '不选择' : stage.text,
          value: stage.value,
          isCustom: false,
        }))
      } else {
        // 根据星期过滤可用的关卡
        baseOptions = STAGE_DAILY_INFO.filter(stage => stage.days.includes(dayNumber)).map(
          stage => ({
            label: taskName === '剩余理智关卡' && stage.value === '-' ? '不选择' : stage.text,
            value: stage.value,
            isCustom: false,
          })
        )
      }

      // 如果当前值是自定义值且不在基础选项中，添加到选项列表
      if (currentValue && isCustomStage(currentValue, columnKey)) {
        const customOption = {
          label: currentValue,
          value: currentValue,
          isCustom: true,
        }
        // 检查是否已存在
        const exists = baseOptions.some(option => option.value === currentValue)
        if (!exists) {
          baseOptions.push(customOption)
        }
      }

      // 添加临时输入的自定义关卡（用于添加新关卡时）
      const customOptions = Object.keys(customStageNames.value)
        .filter(key => customStageNames.value[key] && customStageNames.value[key].trim())
        .filter(key => {
          const value = customStageNames.value[key]
          return !baseOptions.some(option => option.value === value)
        })
        .map(key => ({
          label: customStageNames.value[key],
          value: customStageNames.value[key],
          isCustom: true,
        }))

      return [...baseOptions, ...customOptions]
    }
    default:
      return []
  }
}

// 获取占位符
const getPlaceholder = (taskName: string) => {
  switch (taskName) {
    case '吃理智药':
      return '输入数量'
    case '连战次数':
      return '选择次数'
    case '关卡选择':
    case '备选关卡-1':
    case '备选关卡-2':
    case '备选关卡-3':
      return '1-7'
    case '剩余理智关卡':
      return '不选择'
    default:
      return '请选择'
  }
}

// 列禁用状态
const isColumnDisabled = (columnKey: string): boolean => {
  if (currentMode.value === 'ALL') {
    // 在全局模式下，只允许编辑“全局”列
    return columnKey !== 'ALL'
  }
  if (currentMode.value === 'Weekly') {
    // 在周计划模式下，禁止编辑“全局”列
    return columnKey === 'ALL'
  }
  return false
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
      const planData = response.data[planId] as PlanData

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
          if (
            planData[timeKey] &&
            (planData[timeKey] as Record<string, any>)[fieldKey] !== undefined
          ) {
            ;(row as TableRow)[timeKey] = (planData[timeKey] as Record<string, any>)[fieldKey]
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
        const planId = item.uid
        const planName = response.data[planId]?.Info?.Name || `计划 ${index + 1}`
        return { id: planId, name: planName }
      })

      // 根据路由查询参数尝试选中特定计划
      const queryPlanId = (route.query.planId as string) || ''
      const target = queryPlanId ? planList.value.find(p => p.id === queryPlanId) : null
      if (target) {
        activePlanId.value = target.id
      } else {
        activePlanId.value = planList.value[0].id
      }
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
        ;(planData[timeKey] as Record<string, any>)[row.key] = (row as TableRow)[timeKey]
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

// 自动保存功能
watch(
  () => [currentPlanName.value, currentMode.value],
  async () => {
    // 使用nextTick确保DOM更新后再保存
    await nextTick()
    handleSave()
  }
)
// 单独监听表格数据变化，但减少深度
watch(
  () =>
    tableData.value.map(row => ({
      key: row.key,
      ALL: row.ALL,
      Monday: row.Monday,
      Tuesday: row.Tuesday,
      Wednesday: row.Wednesday,
      Thursday: row.Thursday,
      Friday: row.Friday,
      Saturday: row.Saturday,
      Sunday: row.Sunday,
    })),
  async () => {
    await nextTick()
    handleSave()
  },
  { deep: true }
)

const route = useRoute() // 补充：之前缺失导致无法读取 query

// 监听 planId 查询参数变化（当页面已在 /plans 再次跳转时也能切换）
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

// 简化视图数据
const SIMPLE_VIEW_DATA = STAGE_DAILY_INFO.filter(stage => stage.value !== '-').map(stage => ({
  key: stage.value,
  taskName: stage.text,
  ALL: '-',
  Monday: '-',
  Tuesday: '-',
  Wednesday: '-',
  Thursday: '-',
  Friday: '-',
  Saturday: '-',
  Sunday: '-',
}))

const simpleViewData = ref(SIMPLE_VIEW_DATA)

// 检查关卡是否可用
const isStageAvailable = (stageValue: string, columnKey: string) => {
  if (columnKey === 'ALL') return true

  const dayNumber = getDayNumber(columnKey)
  const stage = STAGE_DAILY_INFO.find(s => s.value === stageValue)
  return stage ? stage.days.includes(dayNumber) : false
}

// 检查关卡是否已启用
const isStageEnabled = (stageValue: string, columnKey: string) => {
  // 检查所有关卡槽位中是否有该关卡
  const stageSlots = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3']
  return stageSlots.some(slot => {
    const row = tableData.value.find(row => row.key === slot) as TableRow | undefined
    return row && row[columnKey] === stageValue
  })
}
// 切换关卡启用状态
const toggleStage = (stageValue: string, columnKey: string, checked: boolean) => {
  const stageSlots = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3']

  if (checked) {
    // 启用关卡：找到第一个空槽位
    for (const slot of stageSlots) {
      const row = tableData.value.find(row => row.key === slot) as TableRow | undefined
      if (row && (row[columnKey] === '-' || row[columnKey] === '')) {
        row[columnKey] = stageValue
        break
      }
    }
  } else {
    // 禁用关卡：从所有槽位中移除
    for (const slot of stageSlots) {
      const row = tableData.value.find(row => row.key === slot) as TableRow | undefined
      if (row && row[columnKey] === stageValue) {
        row[columnKey] = '-'
      }
    }
  }
}
// 获取简化视图任务标签颜色
const getSimpleTaskTagColor = (taskName: string) => {
  const colorMap: Record<string, string> = {
    '当前/上次': 'blue',
    '1-7': 'default',
    'R8-11': 'default',
    '12-17-HARD': 'default',
    '龙门币-6/5': 'blue',
    '红票-5': 'volcano',
    '技能-5': 'cyan',
    '经验-6/5': 'gold',
    '碳-5': 'default',
    '奶/盾芯片': 'green',
    '奶/盾芯片组': 'green',
    '术/狙芯片': 'purple',
    '术/狙芯片组': 'purple',
    '先/辅芯片': 'volcano',
    '先/辅芯片组': 'volcano',
    '近/特芯片': 'red',
    '近/特芯片组': 'red',
  }

  return colorMap[taskName] || 'default'
}

// 启用所有关卡
const enableAllStages = (stageValue: string) => {
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
    if (isStageAvailable(stageValue, timeKey)) {
      // 如果当前状态不是启用状态，则切换
      if (!isStageEnabled(stageValue, timeKey)) {
        toggleStage(stageValue, timeKey, true)
      }
    }
  })
}

// 新增禁用所有关卡的方法
const disableAllStages = (stageValue: string) => {
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
    if (isStageAvailable(stageValue, timeKey)) {
      // 如果当前状态是启用状态，则切换
      if (isStageEnabled(stageValue, timeKey)) {
        toggleStage(stageValue, timeKey, false)
      }
    }
  })
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
  height: 100%;
  padding: 4px 12px;
  font-weight: 500;
  font-size: 13px;
  border-radius: 6px;
  margin: 4px;
}

/* 配置输入组件 */
.config-select {
  width: 100%;
  min-width: 100px;
}

.config-input-number {
  width: 100%;
  min-width: 100px;
  height: 100%;
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

.config-input-number:hover,
.config-input-number:focus,
.config-input-number.ant-input-number-focused {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

.config-input-number :deep(.ant-input-number-input) {
  text-align: center;
  padding: 0 !important;
  margin: 0 !important;
  height: 100%;
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  font-size: 13px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.config-input-number :deep(.ant-input-number-input:focus) {
  box-shadow: none !important;
  border: none !important;
  background: transparent !important;
}

/* 隐藏数字输入框的控制按钮 */
.config-input-number :deep(.ant-input-number-handler-wrap) {
  display: none !important;
}

/* 确保在表格hover时保持一致的背景 */
.config-table :deep(.ant-table-tbody > tr:hover .config-input-number) {
  background: transparent !important;
}

.config-table :deep(.ant-table-tbody > tr:hover .ant-input-number-input) {
  background: transparent !important;
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

  /* 小屏幕上确保表格能够水平滚动 */
  .config-table :deep(.ant-table-content) {
    min-width: 800px; /* 最小宽度确保表格内容不会被挤压 */
  }

  .simple-table :deep(.ant-table-content) {
    min-width: 600px;
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
  padding: 4px 2px;
  vertical-align: middle;
}

.config-table :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--ant-color-bg-container-disabled);
}

.config-table :deep(.ant-table-tbody > tr:hover .ant-select-selector) {
  background: var(--ant-color-bg-container-disabled) !important;
}

.config-table :deep(.ant-table-tbody > tr:hover .ant-input-number) {
  background: var(--ant-color-bg-container-disabled) !important;
}

.config-select :deep(.ant-select-selector) {
  border: none !important;
  border-radius: 0;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0;
  min-height: auto;
}

.config-select :deep(.ant-select-selector:hover) {
  border: none !important;
  box-shadow: none !important;
}

.config-select :deep(.ant-select-focused .ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
}

.config-select :deep(.ant-select-selection-search) {
  margin: 0;
  padding: 0;
}

.config-select :deep(.ant-select-selection-placeholder) {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
  padding: 0;
  margin: 0;
}

.config-select :deep(.ant-select-selection-item) {
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 500;
  padding: 0;
  margin: 0;
  line-height: 1.2;
}

/* 自定义关卡选中时的主题色显示 */
.custom-stage-selected :deep(.ant-select-selection-item) {
  color: var(--ant-color-primary) !important;
  font-weight: 600;
}

/* 隐藏清除按钮 */
.config-select :deep(.ant-select-clear) {
  display: none !important;
}

/* 任务名称单元格背景色 - 浅色主题 */
.config-table :deep(.task-row-MedicineNumb td:first-child) {
  background: #ebf4ff !important; /* 不透明的蓝色背景 */
  color: #3b82f6;
  font-weight: 500;
}

.config-table :deep(.ant-table-tbody > tr.task-row-MedicineNumb:hover > td:first-child) {
  background: #dbeafe !important; /* 悬停时稍深的蓝色 */
}

.config-table :deep(.task-row-SeriesNumb td:first-child) {
  background: #ecfdf5 !important; /* 不透明的绿色背景 */
  color: #22c55e;
  font-weight: 500;
}

.config-table :deep(.ant-table-tbody > tr.task-row-SeriesNumb:hover > td:first-child) {
  background: #d1fae5 !important; /* 悬停时稍深的绿色 */
}

.config-table :deep(.task-row-Stage td:first-child) {
  background: #fff7ed !important; /* 不透明的橙色背景 */
  color: #f97316;
  font-weight: 500;
}

.config-table :deep(.ant-table-tbody > tr.task-row-Stage:hover > td:first-child) {
  background: #fed7aa !important; /* 悬停时稍深的橙色 */
}

.config-table :deep(.task-row-Stage_1 td:first-child),
.config-table :deep(.task-row-Stage_2 td:first-child),
.config-table :deep(.task-row-Stage_3 td:first-child) {
  background: #faf5ff !important; /* 不透明的紫色背景 */
  color: #a855f7;
  font-weight: 500;
}

.config-table :deep(.ant-table-tbody > tr.task-row-Stage_1:hover > td:first-child),
.config-table :deep(.ant-table-tbody > tr.task-row-Stage_2:hover > td:first-child),
.config-table :deep(.ant-table-tbody > tr.task-row-Stage_3:hover > td:first-child) {
  background: #f3e8ff !important; /* 悬停时稍深的紫色 */
}

.config-table :deep(.task-row-Stage_Remain td:first-child) {
  background: #f0f9ff !important; /* 不透明的天蓝色背景 */
  color: #0ea5e9;
  font-weight: 500;
}

.config-table :deep(.ant-table-tbody > tr.task-row-Stage_Remain:hover > td:first-child) {
  background: #e0f2fe !important; /* 悬停时稍深的天蓝色 */
}

/* 任务名称单元格背景色 - 深色主题 */
.dark .config-table :deep(.task-row-MedicineNumb td:first-child) {
  background: #1e3a8a !important; /* 深色蓝色背景 */
  color: #93c5fd;
  font-weight: 500;
}

.dark .config-table :deep(.ant-table-tbody > tr.task-row-MedicineNumb:hover > td:first-child) {
  background: #1e40af !important; /* 悬停时稍亮的蓝色 */
}

.dark .config-table :deep(.task-row-SeriesNumb td:first-child) {
  background: #14532d !important; /* 深色绿色背景 */
  color: #86efac;
  font-weight: 500;
}

.dark .config-table :deep(.ant-table-tbody > tr.task-row-SeriesNumb:hover > td:first-child) {
  background: #166534 !important; /* 悬停时稍亮的绿色 */
}

.dark .config-table :deep(.task-row-Stage td:first-child) {
  background: #7c2d12 !important; /* 深色橙色背景 */
  color: #fdba74;
  font-weight: 500;
}

.dark .config-table :deep(.ant-table-tbody > tr.task-row-Stage:hover > td:first-child) {
  background: #9a3412 !important; /* 悬停时稍亮的橙色 */
}

.dark .config-table :deep(.task-row-Stage_1 td:first-child),
.dark .config-table :deep(.task-row-Stage_2 td:first-child),
.dark .config-table :deep(.task-row-Stage_3 td:first-child) {
  background: #581c87 !important; /* 深色紫色背景 */
  color: #c4b5fd;
  font-weight: 500;
}

.dark .config-table :deep(.ant-table-tbody > tr.task-row-Stage_1:hover > td:first-child),
.dark .config-table :deep(.ant-table-tbody > tr.task-row-Stage_2:hover > td:first-child),
.dark .config-table :deep(.ant-table-tbody > tr.task-row-Stage_3:hover > td:first-child) {
  background: #6b21a8 !important; /* 悬停时稍亮的紫色 */
}

.dark .config-table :deep(.task-row-Stage_Remain td:first-child) {
  background: #0c4a6e !important; /* 深色天蓝色背景 */
  color: #7dd3fc;
  font-weight: 500;
}

.dark .config-table :deep(.ant-table-tbody > tr.task-row-Stage_Remain:hover > td:first-child) {
  background: #075985 !important; /* 悬停时稍亮的天蓝色 */
}

/* 确保固定列在滚动时背景不透明 */
.config-table :deep(.ant-table-fixed-left) {
  background: var(--ant-color-bg-container) !important;
}

.config-table :deep(.ant-table-thead > tr > th.ant-table-fixed-left) {
  background: var(--ant-color-bg-container) !important;
  border-right: 1px solid var(--ant-color-border);
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.05);
}

/* 专门处理"配置项"表头单元格 */
.config-table :deep(.ant-table-thead > tr > th:first-child) {
  background: var(--ant-color-bg-container) !important;
  border-right: 1px solid var(--ant-color-border);
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.05);
  position: relative;
  z-index: 2;
}

.config-table :deep(.ant-table-tbody > tr > td.ant-table-fixed-left) {
  background: var(--ant-color-bg-container) !important;
  border-right: 1px solid var(--ant-color-border-secondary);
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.05);
}

/* 深色主题下确保第一列背景不透明 */
.dark .config-table :deep(.ant-table-thead > tr > th:first-child) {
  background: var(--ant-color-bg-container) !important;
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.2);
}

.dark .config-table :deep(.ant-table-tbody > tr > td:first-child) {
  background: var(--ant-color-bg-container) !important;
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.2);
}

.dark .config-table :deep(.ant-table-tbody > tr > td.ant-table-fixed-left) {
  background: var(--ant-color-bg-container) !important;
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.2);
}

/* 禁用列标题样式 */
.config-table.mode-ALL :deep(.ant-table-thead > tr > th:nth-child(n + 3)) {
  color: var(--ant-color-text-disabled) !important;
  opacity: 0.5;
}

.config-table.mode-Weekly :deep(.ant-table-thead > tr > th:nth-child(2)) {
  color: var(--ant-color-text-disabled) !important;
  opacity: 0.5;
}

/* 禁用状态样式 */
.config-select:disabled,
.config-select.ant-select-disabled :deep(.ant-select-selector) {
  background: var(--ant-color-bg-container-disabled) !important;
  color: var(--ant-color-text-disabled) !important;
  cursor: default !important;
}

.config-input-number:disabled,
.config-input-number.ant-input-number-disabled :deep(.ant-input-number-input) {
  background: var(--ant-color-bg-container-disabled) !important;
  color: var(--ant-color-text-disabled) !important;
  cursor: default !important;
}

/* 确保悬停时也不显示禁止图标 */
.config-select:disabled:hover,
.config-select.ant-select-disabled:hover :deep(.ant-select-selector),
.config-input-number:disabled:hover,
.config-input-number.ant-input-number-disabled:hover :deep(.ant-input-number-input) {
  cursor: default !important;
}

/* 隐藏下拉箭头或调整样式 */
.config-select :deep(.ant-select-arrow) {
  right: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 10px;
}

.config-select :deep(.ant-select-arrow:hover) {
  color: var(--ant-color-primary);
}

/* 自定义下拉框样式 - 增加下拉菜单宽度 */
.config-select :deep(.ant-select-dropdown) {
  min-width: 280px !important;
  max-width: 400px !important;
}

.config-select :deep(.ant-select-item) {
  padding: 8px 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 自定义关卡选项的样式 */
.config-select :deep(.ant-select-item-option-content) {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  width: 100%;
  min-width: 0;
}

.config-select :deep(.ant-select-item .ant-tag) {
  margin-left: 8px;
  flex-shrink: 0;
}

/* 自定义输入区域样式 */
.config-select :deep(.ant-select-dropdown .ant-divider) {
  margin: 4px 0;
}

.config-select :deep(.ant-select-dropdown .ant-space) {
  padding: 8px 12px;
  background: var(--ant-color-bg-container);
  border-top: 1px solid var(--ant-color-border-secondary);
}

.config-select :deep(.ant-select-dropdown .ant-input) {
  flex: 1;
  min-width: 0;
}

.config-select :deep(.ant-select-dropdown .ant-btn) {
  flex-shrink: 0;
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

/* 全局控制按钮样式 */
.global-control-buttons {
  display: flex;
  gap: 6px;
}

.global-control-button {
  min-width: 32px;
  height: 24px;
  font-size: 12px;
  padding: 0 4px;
}

/* 简化视图表格样式 */
.simple-table :deep(.ant-table-thead > tr > th) {
  background: var(--ant-color-bg-container-disabled);
  border-bottom: 2px solid var(--ant-color-border);
  font-weight: 600;
  color: var(--ant-color-text);
  text-align: center;
  padding: 12px 8px;
  font-size: 13px;
}

.simple-table :deep(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  text-align: center;
  padding: 8px 6px;
  vertical-align: middle;
}

.simple-table :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--ant-color-bg-container-disabled);
}

/* 简化视图表格滚动条样式 */
.simple-table :deep(.ant-table-content) {
  overflow-x: auto;
}

/* 深色主题滚动条样式 - 简化视图 */
.dark .simple-table :deep(.ant-table-content)::-webkit-scrollbar {
  height: 8px;
}

.dark .simple-table :deep(.ant-table-content)::-webkit-scrollbar-track {
  background: var(--ant-color-bg-layout);
  border-radius: 4px;
}

.dark .simple-table :deep(.ant-table-content)::-webkit-scrollbar-thumb {
  background: var(--ant-color-border);
  border-radius: 4px;
  transition: background 0.2s ease;
}

.dark .simple-table :deep(.ant-table-content)::-webkit-scrollbar-thumb:hover {
  background: var(--ant-color-text-tertiary);
}

/* 浅色主题滚动条样式 - 简化视图 */
.simple-table :deep(.ant-table-content)::-webkit-scrollbar {
  height: 8px;
}

.simple-table :deep(.ant-table-content)::-webkit-scrollbar-track {
  background: #f5f5f5;
  border-radius: 4px;
}

.simple-table :deep(.ant-table-content)::-webkit-scrollbar-thumb {
  background: #d9d9d9;
  border-radius: 4px;
  transition: background 0.2s ease;
}

.simple-table :deep(.ant-table-content)::-webkit-scrollbar-thumb:hover {
  background: #bfbfbf;
}

/* Firefox 滚动条样式 - 简化视图 */
.dark .simple-table :deep(.ant-table-content) {
  scrollbar-width: thin;
  scrollbar-color: var(--ant-color-border) var(--ant-color-bg-layout);
}

.simple-table :deep(.ant-table-content) {
  scrollbar-width: thin;
  scrollbar-color: #d9d9d9 #f5f5f5;
}

/* 确保简化视图固定列正确显示 */
.simple-table :deep(.ant-table-thead > tr > th.ant-table-fixed-left) {
  background: var(--ant-color-bg-container) !important;
  border-right: 1px solid var(--ant-color-border);
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.05);
}

.simple-table :deep(.ant-table-tbody > tr > td.ant-table-fixed-left) {
  background: var(--ant-color-bg-container) !important;
  border-right: 1px solid var(--ant-color-border-secondary);
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.05);
}

.dark .simple-table :deep(.ant-table-thead > tr > th.ant-table-fixed-left) {
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.2);
}

.dark .simple-table :deep(.ant-table-tbody > tr > td.ant-table-fixed-left) {
  box-shadow: 2px 0 4px rgba(0, 0, 0, 0.2);
}

/* 拖拽视觉反馈 */
.simple-table :deep(.ant-table-row.drag-over) {
  border-top: 2px solid var(--ant-color-primary);
}

.simple-table :deep(.ant-table-row.dragging) {
  opacity: 0.5;
}

/* 水平滚动条样式 */
.config-table-container {
  /* 移除容器的滚动，让Ant Design表格自己处理 */
  width: 100%;
}

.config-table-wrapper {
  /* 移除wrapper的滚动，避免双滚动条 */
  width: 100%;
}

.simple-table-wrapper {
  /* 移除wrapper的滚动，避免双滚动条 */
  width: 100%;
}

/* 为配置表格添加更好的滚动条样式 */
.config-table :deep(.ant-table-content) {
  /* 让Ant Design表格自己处理滚动 */
  overflow-x: auto;
}

/* 深色主题滚动条样式 - 针对表格内容区域 */
.dark .config-table :deep(.ant-table-content)::-webkit-scrollbar {
  height: 8px;
}

.dark .config-table :deep(.ant-table-content)::-webkit-scrollbar-track {
  background: var(--ant-color-bg-layout);
  border-radius: 4px;
}

.dark .config-table :deep(.ant-table-content)::-webkit-scrollbar-thumb {
  background: var(--ant-color-border);
  border-radius: 4px;
  transition: background 0.2s ease;
}

.dark .config-table :deep(.ant-table-content)::-webkit-scrollbar-thumb:hover {
  background: var(--ant-color-text-tertiary);
}

/* 浅色主题滚动条样式 - 针对表格内容区域 */
.config-table :deep(.ant-table-content)::-webkit-scrollbar {
  height: 8px;
}

.config-table :deep(.ant-table-content)::-webkit-scrollbar-track {
  background: #f5f5f5;
  border-radius: 4px;
}

.config-table :deep(.ant-table-content)::-webkit-scrollbar-thumb {
  background: #d9d9d9;
  border-radius: 4px;
  transition: background 0.2s ease;
}

.config-table :deep(.ant-table-content)::-webkit-scrollbar-thumb:hover {
  background: #bfbfbf;
}

/* 确保表格在小屏幕上能够水平滚动 */
@media (max-width: 1200px) {
  .config-table-container {
    /* 移除重复的overflow-x，避免双滚动条 */
    -webkit-overflow-scrolling: touch;
  }
}

/* Firefox 滚动条样式 - 针对表格内容区域 */
.dark .config-table :deep(.ant-table-content) {
  scrollbar-width: thin;
  scrollbar-color: var(--ant-color-border) var(--ant-color-bg-layout);
}

.config-table :deep(.ant-table-content) {
  scrollbar-width: thin;
  scrollbar-color: #d9d9d9 #f5f5f5;
}
</style>
