<template>
  <div>
    <div v-if="viewMode === 'config'" class="config-table-wrapper">
      <a-table
        :columns="dynamicTableColumns"
        :data-source="rows"
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
              v-model:value="(record as any)[column.key]"
              size="small"
              :min="0"
              :max="999"
              :placeholder="getPlaceholder(record.taskName)"
              class="config-input-number"
              :controls="false"
              :bordered="false"
              :disabled="isColumnDisabled(column.key as string)"
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
              v-model:value="(record as any)[column.key]"
              size="small"
              :placeholder="getPlaceholder(record.taskName)"
              :class="[
                'config-select',
                {
                  'custom-stage-selected': isCustomStage(
                    (record as any)[column.key] as string,
                    column.key as string
                  ),
                },
              ]"
              allow-clear
              :bordered="false"
              :disabled="isColumnDisabled(column.key as string)"
            >
              <template #dropdownRender="{ menuNode: menu }">
                <component :is="VNodeRenderer" :vnodes="menu" />
                <a-divider style="margin: 4px 0" />
                <a-space style="padding: 4px 8px" size="small">
                  <a-input
                    v-model:value="customStageNames[`${record.key}_${String(column.key)}`]"
                    placeholder="自定义"
                    style="flex: 1"
                    size="small"
                    :bordered="false"
                    class="config-text-input"
                    @keyup.enter="addCustomStage(record.key, column.key as string)"
                  />
                  <a-button
                    type="text"
                    size="small"
                    @click="addCustomStage(record.key, column.key as string)"
                  >
                    <template #icon>
                      <PlusOutlined />
                    </template>
                  </a-button>
                </a-space>
              </template>

              <a-select-option
                v-for="option in getSelectOptions(
                  column.key as string,
                  record.taskName,
                  (record as any)[column.key] as string
                )"
                :key="option.value"
                :value="option.value"
              >
                <template v-if="option.label && String(option.label).includes('|')">
                  <span>{{ String(option.label).split('|')[0] }}</span>
                  <a-tag color="green" size="small" style="margin-left: 8px">
                    {{ String(option.label).split('|')[1] }}
                  </a-tag>
                </template>
                <template v-else>
                  <span
                    :style="
                      isCustomStage(option.value, column.key as string)
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
              v-model:value="(record as any)[column.key]"
              size="small"
              :options="
                getSelectOptions(
                  column.key as string,
                  record.taskName,
                  (record as any)[column.key] as string
                )
              "
              :placeholder="getPlaceholder(record.taskName)"
              class="config-select"
              allow-clear
              :bordered="false"
              :disabled="isColumnDisabled(column.key as string)"
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
          <template v-if="column.key === 'globalControl'">
            <a-space>
              <a-tooltip title="开/关所有可用关卡" placement="left">
                <a-button ghost size="small" type="primary" @click="enableAllStages(record.key)"
                  >开
                </a-button>
              </a-tooltip>
              <a-button size="small" danger @click="disableAllStages(record.key)">关</a-button>
            </a-space>
          </template>

          <template v-else-if="column.key === 'taskName'">
            <div class="task-name-cell">
              <a-tag :color="getSimpleTaskTagColor(record.taskName)" class="task-tag"
                >{{ record.taskName }}
              </a-tag>
            </div>
          </template>

          <template v-else>
            <div v-if="isStageAvailable(record.key, column.key as string)">
              <a-switch
                :checked="isStageEnabled(record.key, column.key as string)"
                @change="
                  (checked: boolean) => toggleStage(record.key, column.key as string, checked)
                "
              />
            </div>
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'

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

  [key: string]: string | number
}

interface Props {
  tableData: Record<string, any> | null
  currentMode: 'ALL' | 'Weekly'
  viewMode: 'config' | 'simple'
}

// 添加一个新的prop用于控制选项是否已加载
interface ExtendedProps extends Props {
  optionsLoaded?: boolean
}

interface Emits {
  (e: 'update-table-data', value: Record<string, any>): void
}

const props = defineProps<ExtendedProps>()
const emit = defineEmits<Emits>()

// 添加一个响应式变量来跟踪选项是否已加载
const localOptionsLoaded = ref(false)

// 在组件挂载后延迟加载选项数据
onMounted(() => {
  // 使用setTimeout延迟加载选项，让表格先渲染出来
  setTimeout(() => {
    localOptionsLoaded.value = true
    // 清除缓存以确保重新计算选项
    stageOptionsCache.value.clear()
  }, 0)
})

// 当tableData发生变化且有数据时，确保选项已加载
watch(
  () => props.tableData,
  newData => {
    if (newData && Object.keys(newData).length > 0 && !localOptionsLoaded.value) {
      localOptionsLoaded.value = true
      // 清除缓存以确保重新计算选项
      stageOptionsCache.value.clear()
    }
  },
  { immediate: true }
)

// 渲染VNode的辅助组件
const VNodeRenderer = defineComponent({
  name: 'VNodeRenderer',
  props: { vnodes: { type: Object, required: true } },
  setup(p) {
    return () => p.vnodes as any
  },
})

// 改回使用普通的ref，确保响应式正常工作
const rows = ref<TableRow[]>([
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

// 列配置
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
  { title: '全局', dataIndex: 'ALL', key: 'ALL', width: 120, align: 'center' },
  { title: '周一', dataIndex: 'Monday', key: 'Monday', width: 120, align: 'center' },
  { title: '周二', dataIndex: 'Tuesday', key: 'Tuesday', width: 120, align: 'center' },
  { title: '周三', dataIndex: 'Wednesday', key: 'Wednesday', width: 120, align: 'center' },
  { title: '周四', dataIndex: 'Thursday', key: 'Thursday', width: 120, align: 'center' },
  { title: '周五', dataIndex: 'Friday', key: 'Friday', width: 120, align: 'center' },
  { title: '周六', dataIndex: 'Saturday', key: 'Saturday', width: 120, align: 'center' },
  { title: '周日', dataIndex: 'Sunday', key: 'Sunday', width: 120, align: 'center' },
])

const dynamicTableColumns = computed(() => tableColumns.value)

// 简化视图列
const dynamicSimpleViewColumns = computed(() => [
  { title: '全局控制', key: 'globalControl', width: 75, fixed: 'left', align: 'center' },
  {
    title: '关卡',
    dataIndex: 'taskName',
    key: 'taskName',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  ...tableColumns.value.filter(col => col.key !== 'taskName' && col.key !== 'globalControl'),
])

// 关卡日历
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

const getDayNumber = (columnKey: string) =>
  (
    ({
      ALL: 0,
      Monday: 1,
      Tuesday: 2,
      Wednesday: 3,
      Thursday: 4,
      Friday: 5,
      Saturday: 6,
      Sunday: 7,
    }) as Record<string, number>
  )[columnKey] || 0

// 自定义关卡
const customStageNames = ref<Record<string, string>>({})

const addCustomStage = (rowKey: string, columnKey: string) => {
  const inputName = `${rowKey}_${columnKey}`
  const customName = customStageNames.value[inputName]

  if (!customName || !customName.trim()) {
    message.warning('请输入关卡名称')
    return
  }

  const stagePattern = /^[A-Za-z0-9\-_]+$/
  if (!stagePattern.test(customName.trim())) {
    message.warning('关卡名称只能包含字母、数字、短横线和下划线')
    return
  }

  const exists = stageOptions.value.find(option => option.value === customName.trim())
  if (exists) {
    message.warning('该关卡已存在')
    return
  }

  customStageNames.value[customName.trim()] = customName.trim()
  const targetRow = rows.value.find(row => row.key === rowKey)
  if (targetRow) {
    ;(targetRow as any)[columnKey] = customName.trim()
  }
  customStageNames.value[inputName] = ''
  message.success('关卡添加成功')
}

// 缓存计算属性，避免重复计算
const stageOptionsCache = ref(new Map<string, any[]>())

// 修改stageOptions计算属性，仅在选项已加载时才计算
const stageOptions = computed(() => {
  // 如果通过props传入了optionsLoaded且为true，或者本地状态表示已加载，则计算选项
  const optionsReady = props.optionsLoaded || localOptionsLoaded.value
  if (!optionsReady) {
    return []
  }

  const cacheKey = 'base_stage_options'
  if (!stageOptionsCache.value.has(cacheKey)) {
    const baseOptions = STAGE_DAILY_INFO.map(stage => ({
      label: stage.text,
      value: stage.value,
      isCustom: false,
    }))
    const customOptions = Object.keys(customStageNames.value).map(key => ({
      label: customStageNames.value[key],
      value: key,
      isCustom: true,
    }))
    stageOptionsCache.value.set(cacheKey, [...baseOptions, ...customOptions])
  }
  return stageOptionsCache.value.get(cacheKey) || []
})

// 修改getSelectOptions函数，添加选项未加载时的默认处理
const getSelectOptions = (columnKey: string, taskName: string, currentValue?: string) => {
  // 如果选项未加载，返回包含当前值的简单选项或空数组
  const optionsReady = props.optionsLoaded || localOptionsLoaded.value
  if (!optionsReady) {
    if (currentValue) {
      // 如果有当前值，至少返回包含当前值的选项，避免显示空白
      return [{ label: currentValue, value: currentValue }]
    }
    return []
  }

  const cacheKey = `${columnKey}_${taskName}_${currentValue || ''}`

  if (stageOptionsCache.value.has(cacheKey)) {
    return stageOptionsCache.value.get(cacheKey)
  }

  let options: any[]

  switch (taskName) {
    case '连战次数':
      options = [
        { label: 'AUTO', value: '0' },
        { label: '1', value: '1' },
        { label: '2', value: '2' },
        { label: '3', value: '3' },
        { label: '4', value: '4' },
        { label: '5', value: '5' },
        { label: '6', value: '6' },
        { label: '不切换', value: '-1' },
      ]
      break
    case '关卡选择':
    case '备选关卡-1':
    case '备选关卡-2':
    case '备选关卡-3':
    case '剩余理智关卡': {
      const dayNumber = getDayNumber(columnKey)
      let baseOptions: any[] = []
      if (dayNumber === 0) {
        baseOptions = STAGE_DAILY_INFO.map(stage => ({
          label: taskName === '剩余理智关卡' && stage.value === '-' ? '不选择' : stage.text,
          value: stage.value,
          isCustom: false,
        }))
      } else {
        baseOptions = STAGE_DAILY_INFO.filter(stage => stage.days.includes(dayNumber)).map(
          stage => ({
            label: taskName === '剩余理智关卡' && stage.value === '-' ? '不选择' : stage.text,
            value: stage.value,
            isCustom: false,
          })
        )
      }
      if (currentValue && isCustomStage(currentValue, columnKey)) {
        const exists = baseOptions.some(option => option.value === currentValue)
        if (!exists) baseOptions.push({ label: currentValue, value: currentValue, isCustom: true })
      }
      const customOptions = Object.keys(customStageNames.value)
        .filter(key => customStageNames.value[key] && customStageNames.value[key].trim())
        .filter(key => !baseOptions.some(option => option.value === customStageNames.value[key]))
        .map(key => ({
          label: customStageNames.value[key],
          value: customStageNames.value[key],
          isCustom: true,
        }))
      options = [...baseOptions, ...customOptions]
      break
    }
    default:
      options = []
  }

  // 缓存结果
  stageOptionsCache.value.set(cacheKey, options)
  return options
}

const isCustomStage = (value: string, columnKey: string) => {
  if (!value || value === '-') return false
  const dayNumber = getDayNumber(columnKey)
  let availableStages: string[]
  if (dayNumber === 0) {
    availableStages = STAGE_DAILY_INFO.map(stage => stage.value)
  } else {
    availableStages = STAGE_DAILY_INFO.filter(stage => stage.days.includes(dayNumber)).map(
      stage => stage.value
    )
  }
  return !availableStages.includes(value)
}

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

const isColumnDisabled = (columnKey: string): boolean => {
  if (props.currentMode === 'ALL') return columnKey !== 'ALL'
  if (props.currentMode === 'Weekly') return columnKey === 'ALL'
  return false
}

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

const isStageAvailable = (stageValue: string, columnKey: string) => {
  if (columnKey === 'ALL') return true
  const dayNumber = getDayNumber(columnKey)
  const stage = STAGE_DAILY_INFO.find(s => s.value === stageValue)
  return stage ? stage.days.includes(dayNumber) : false
}

const isStageEnabled = (stageValue: string, columnKey: string) => {
  const stageSlots = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3']
  return stageSlots.some(slot => {
    const row = rows.value.find(r => r.key === slot) as TableRow | undefined
    return row && (row as any)[columnKey] === stageValue
  })
}

const toggleStage = (stageValue: string, columnKey: string, checked: boolean) => {
  const stageSlots = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3']
  const newRows = [...rows.value]

  if (checked) {
    for (const slot of stageSlots) {
      const row = newRows.find(r => r.key === slot) as TableRow | undefined
      if (row && ((row as any)[columnKey] === '-' || (row as any)[columnKey] === '')) {
        ;(row as any)[columnKey] = stageValue
        break
      }
    }
  } else {
    for (const slot of stageSlots) {
      const row = newRows.find(r => r.key === slot) as TableRow | undefined
      if (row && (row as any)[columnKey] === stageValue) {
        ;(row as any)[columnKey] = '-'
      }
    }
  }

  rows.value = newRows
}

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
      if (!isStageEnabled(stageValue, timeKey)) toggleStage(stageValue, timeKey, true)
    }
  })
}

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
      if (isStageEnabled(stageValue, timeKey)) toggleStage(stageValue, timeKey, false)
    }
  })
}

// 从 rows 组装为 API 所需结构
const buildPlanDataFromRows = (): Record<string, any> => {
  const planData: Record<string, any> = {}
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
    rows.value.forEach(row => {
      ;(planData[timeKey] as Record<string, any>)[row.key] = (row as any)[timeKey]
    })
  })
  return planData
}

// 优化数据同步，但保持响应式
const applyPlanDataToRows = (plan: Record<string, any> | null | undefined) => {
  if (!plan) return

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

  rows.value.forEach(row => {
    const fieldKey = row.key
    timeKeys.forEach(timeKey => {
      if (plan[timeKey] && plan[timeKey][fieldKey] !== undefined) {
        ;(row as any)[timeKey] = plan[timeKey][fieldKey]
      }
    })
  })

  // 清除缓存以重新计算选项
  stageOptionsCache.value.clear()
}

// 简化的防抖函数
const debounce = <T extends (...args: any[]) => any>(func: T, wait: number): T => {
  let timeout: NodeJS.Timeout | null = null
  return ((...args: any[]) => {
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(() => func(...args), wait)
  }) as T
}

const debouncedEmitUpdate = debounce(() => {
  emit('update-table-data', buildPlanDataFromRows())
}, 150)

// 恢复正常的watch监听
watch(
  () => props.tableData,
  newVal => {
    applyPlanDataToRows(newVal || {})
  },
  { immediate: true, deep: true }
)

// 监听rows变化并触发更新
watch(
  rows,
  () => {
    debouncedEmitUpdate()
  },
  { deep: true }
)
</script>

<style scoped>
/* Inputs/selects: borderless + centered */
.config-select {
  width: 100%;
  min-width: 100px;
}

.config-input-number {
  width: 100%;
  min-width: 100px;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}

.config-input-number:hover,
.config-input-number:focus,
.config-input-number:active {
  border: none !important;
  box-shadow: none !important;
}

.config-input-number input {
  text-align: center;
}

/* Ensure centered text in all states for Ant Design Vue InputNumber */
.config-input-number :deep(.ant-input-number-input) {
  text-align: center;
}

/* Remove number input handlers spacing (already controls=false) */
.config-input-number :deep(.ant-input-number-handler-wrap) {
  display: none;
}

/* Select: borderless */
.config-select :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

.config-select :deep(.ant-select-focused .ant-select-selector),
.config-select :deep(.ant-select:hover .ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
}

/* Center selected text and placeholder */
.config-select :deep(.ant-select-selection-item),
.config-select :deep(.ant-select-selection-placeholder) {
  width: 100%;
  text-align: center;
  margin-inline-start: 0 !important;
}

/* Clear icon alignment without shifting text */
.config-select :deep(.ant-select-clear) {
  right: 4px;
}

/* Disabled states keep borderless look */
.config-select :deep(.ant-select-disabled .ant-select-selector) {
  background: transparent !important;
}

/* Borderless text input in dropdown */
.config-text-input {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  text-align: center;
}

.config-text-input:hover,
.config-text-input:focus {
  border: none !important;
  box-shadow: none !important;
}

.task-name-cell {
  display: flex;
  justify-content: center;
}

/* Ensure table body cell content stays centered visually */
:deep(.config-table .ant-table-tbody > tr > td) {
  text-align: center;
}
</style>
