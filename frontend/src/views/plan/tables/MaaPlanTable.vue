<template>
  <div>
    <!-- 配置视图 -->
    <div v-show="viewMode === 'config'" class="config-table-wrapper">
      <a-table :key="`config-table-${currentMode}`" :columns="configColumns"
        :data-source="coordinator.configViewData.value" :pagination="false"
        :class="['config-table', `mode-${currentMode}`]" size="middle" :bordered="true" :scroll="{ x: 'max-content' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'taskName'">
            {{ record.taskName }}
          </template>

          <template v-else-if="record.taskName === '吃理智药'">
            <a-input-number :value="(record as any)[column.key]" size="small" :min="0" :max="999"
              class="config-input-number" :controls="false" :bordered="false"
              :disabled="isColumnDisabled(column.key as string)"
              @update:value="updateConfigValue(record.key, column.key as TimeKey, $event)" />
          </template>

          <template v-else>
            <a-select :value="(record as any)[column.key]" size="small" :class="[
              'config-select',
              {
                'custom-stage-selected': isCustomStage((record as any)[column.key]),
              },
            ]" allow-clear :bordered="false" :disabled="isColumnDisabled(column.key as string)"
              @update:value="updateConfigValue(record.key, column.key as TimeKey, $event)">
              <a-select-option v-for="option in getSelectOptions(
                column.key as string,
                record.taskName,
                (record as any)[column.key] as string
              )" :key="option.value" :value="option.value" :disabled="option.disabled"
                :class="{ 'custom-stage-option': isCustomStage(option.value) }">
                <span :style="{
                  color: isCustomStage(option.value) ? 'var(--ant-color-primary)' : undefined,
                  fontWeight: isCustomStage(option.value) ? '500' : 'normal',
                }">
                  {{ option.label }}
                </span>
              </a-select-option>
            </a-select>
          </template>
        </template>
      </a-table>
    </div>

    <!-- 简化视图 -->
    <div v-show="viewMode === 'simple'" class="simple-table-wrapper">
      <a-table :key="`simple-table-${currentMode}`" :columns="simpleColumns"
        :data-source="coordinator.simpleViewData.value" :pagination="false" class="simple-table" size="small"
        :bordered="true" :scroll="{ x: 'max-content' }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'globalControl'">
            <a-space>
              <a-button ghost size="small" type="primary" @click="enableAllStages(record.key)">开</a-button>
              <a-button size="small" danger @click="disableAllStages(record.key)">关</a-button>
            </a-space>
          </template>

          <template v-else-if="column.key === 'taskName'">
            <a-tag :color="getStageTagColor(record.taskName, record.isCustom)" class="task-tag"
              :class="{ 'custom-stage-tag': record.isCustom }">
              {{ record.taskName }}
            </a-tag>
          </template>

          <template v-else>
            <a-switch v-if="isStageAvailable(record.key, column.key as string)" :checked="record[column.key]"
              :disabled="isSwitchDisabled(column.key as string, record)"
              @change="handleStageToggle(record.key, column.key as TimeKey, $event)" />
          </template>
        </template>
      </a-table>
    </div>

    <!-- 自定义关卡设置区域 -->
    <div class="custom-stage-section" style="margin-top: 16px">
      <a-row :gutter="24">
        <a-col v-for="i in 4" :key="i" :span="6">
          <a-form-item :colon="false" class="compact-form-item">
            <template #label>
              <a-tooltip title="关卡选择中可选的自定义关卡号">
                <span class="form-label">
                  自定义关卡 {{ i }}
                  <QuestionCircleOutlined class="help-icon" />
                </span>
              </a-tooltip>
            </template>
            <a-input v-model:value="tempCustomStages[`custom_stage_${i}` as keyof typeof tempCustomStages]"
              placeholder="输入关卡号" :maxlength="50" allow-clear size="large" class="modern-input"
              @input="onCustomStageInput(i as 1 | 2 | 3 | 4)" @blur="onCustomStageBlurOrEnter(i as 1 | 2 | 3 | 4)"
              @press-enter="onCustomStageBlurOrEnter(i as 1 | 2 | 3 | 4)" />
          </a-form-item>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import {
  usePlanDataCoordinator,
  type TimeKey,
  preloadAllStageOptions,
  getCachedStageOptions,
} from '@/composables/usePlanDataCoordinator'

interface Props {
  tableData: Record<string, any> | null
  currentMode: 'ALL' | 'Weekly'
  viewMode: 'config' | 'simple'
  planId?: string
  handlePlanChange: (path: string, value: any) => Promise<void>
}

const props = defineProps<Props>()

// 使用数据协调器 - 单一数据源
const coordinator = usePlanDataCoordinator()

// 临时自定义关卡输入
const tempCustomStages = ref({
  custom_stage_1: '',
  custom_stage_2: '',
  custom_stage_3: '',
  custom_stage_4: '',
})

// 用于触发下拉框选项刷新的响应式变量
const customStageVersion = ref(0)

// 计算属性：获取当前的自定义关卡列表（用于响应式更新）
const currentCustomStages = computed(() => {
  // 访问 customStageVersion 以触发响应式更新
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  customStageVersion.value

  return Object.values(coordinator.planData.customStageDefinitions).filter(stageName =>
    stageName?.trim()
  )
})

// 配置视图列定义
const configColumns = [
  {
    title: '配置项',
    dataIndex: 'taskName',
    key: 'taskName',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  { title: '全局', dataIndex: 'ALL', key: 'ALL', width: 120, align: 'center' },
  { title: '周一', dataIndex: 'Monday', key: 'Monday', width: 120, align: 'center' },
  { title: '周二', dataIndex: 'Tuesday', key: 'Tuesday', width: 120, align: 'center' },
  { title: '周三', dataIndex: 'Wednesday', key: 'Wednesday', width: 120, align: 'center' },
  { title: '周四', dataIndex: 'Thursday', key: 'Thursday', width: 120, align: 'center' },
  { title: '周五', dataIndex: 'Friday', key: 'Friday', width: 120, align: 'center' },
  { title: '周六', dataIndex: 'Saturday', key: 'Saturday', width: 120, align: 'center' },
  { title: '周日', dataIndex: 'Sunday', key: 'Sunday', width: 120, align: 'center' },
]

// 简化视图列定义
const simpleColumns = [
  { title: '全局控制', key: 'globalControl', width: 75, fixed: 'left', align: 'center' },
  {
    title: '关卡',
    dataIndex: 'taskName',
    key: 'taskName',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  ...configColumns.filter(col => col.key !== 'taskName'),
]

// 更新配置数据 - 直接调用父组件的保存函数
const updateConfigValue = async (rowKey: string, timeKey: TimeKey, value: any) => {
  // 更新本地状态
  coordinator.updateConfig(timeKey, rowKey, value)

  // 构建后端 API 路径，例如 "Monday.Stage" 或 "Monday.MedicineNumb"
  const apiPath = `${timeKey}.${rowKey}`
  await props.handlePlanChange(apiPath, value)
}

// 自定义关卡保存 - 失去焦点或按回车时保存
const saveCustomStage = async (index: 1 | 2 | 3 | 4) => {
  const key = `custom_stage_${index}` as keyof typeof tempCustomStages.value
  const newValue = tempCustomStages.value[key].trim()
  const oldValue = coordinator.planData.customStageDefinitions[key]

  // 如果值没有变化，不需要保存
  if (newValue === oldValue) {
    return
  }

  // 更新自定义关卡定义
  coordinator.updateCustomStageDefinition(index, newValue)

  // 保存自定义关卡涉及更新所有使用它的时间配置
  // 需要将所有关卡配置一起保存
  const planConfig = coordinator.toApiData()

  // 找出哪些时间配置使用了旧的自定义关卡，更新为新值
  const timeKeys: TimeKey[] = [
    'ALL',
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ]
  for (const timeKey of timeKeys) {
    const timeConfig = planConfig[timeKey] as Record<string, any>
    if (timeConfig) {
      // 检查每个关卡字段是否使用了旧的自定义关卡
      const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3', 'Stage_Remain']
      for (const field of stageFields) {
        if (timeConfig[field] === oldValue && oldValue !== '') {
          // 更新为新值
          timeConfig[field] = newValue
        }
      }
      // 保存更新后的时间配置
      await props.handlePlanChange(timeKey, timeConfig)
    }
  }
}

// 自定义关卡输入变化 - 仅更新本地状态以刷新下拉框选项
const onCustomStageInput = (index: 1 | 2 | 3 | 4) => {
  // 立即触发下拉框选项刷新
  customStageVersion.value++

  // 临时更新协调器中的定义（用于下拉框显示）
  const key = `custom_stage_${index}` as keyof typeof tempCustomStages.value
  coordinator.updateCustomStageDefinition(index, tempCustomStages.value[key].trim())
}

// 自定义关卡失去焦点或按回车时保存
const onCustomStageBlurOrEnter = (index: 1 | 2 | 3 | 4) => {
  saveCustomStage(index)
}

// 连战次数选项
const SERIES_OPTIONS: SelectOption[] = [
  { label: 'AUTO', value: '0' },
  { label: '1', value: '1' },
  { label: '2', value: '2' },
  { label: '3', value: '3' },
  { label: '4', value: '4' },
  { label: '5', value: '5' },
  { label: '6', value: '6' },
  { label: '不切换', value: '-1' },
]

// 选项类型定义
interface SelectOption {
  label: string
  value: string
  disabled?: boolean
}

// 获取选择框选项
const getSelectOptions = (
  columnKey: string,
  taskName: string,
  currentValue: string
): SelectOption[] => {
  if (taskName === '连战次数') {
    return SERIES_OPTIONS
  }

  // 关卡选择选项 - 从 API 缓存获取
  const cachedOptions = getCachedStageOptions(columnKey as TimeKey)
  const baseOptions: SelectOption[] = cachedOptions.map(option => ({
    label: option.label,
    value: option.value || '-',
  }))

  // 添加自定义关卡选项（使用计算属性以确保响应式）
  currentCustomStages.value.forEach(stageName => {
    baseOptions.push({ label: stageName, value: stageName })
  })

  // 标记已使用的关卡
  const usedStages = getUsedStagesInColumn(columnKey)
  return baseOptions.map(option => ({
    ...option,
    disabled: usedStages.includes(option.value) && option.value !== currentValue,
    label:
      usedStages.includes(option.value) && option.value !== currentValue
        ? `${option.label} (已选择)`
        : option.label,
  }))
}

// 获取已使用的关卡
const getUsedStagesInColumn = (columnKey: string): string[] => {
  const config = coordinator.planData.timeConfigs[columnKey as TimeKey]
  if (!config) return []

  return Object.values(config.stages).filter(stage => stage && stage !== '-')
}

// 工具函数
const DAY_NUMBER_MAP = {
  ALL: 0,
  Monday: 1,
  Tuesday: 2,
  Wednesday: 3,
  Thursday: 4,
  Friday: 5,
  Saturday: 6,
  Sunday: 7,
} as const

const getDayNumber = (columnKey: string) =>
  DAY_NUMBER_MAP[columnKey as keyof typeof DAY_NUMBER_MAP] || 0

const isColumnDisabled = (columnKey: string): boolean => {
  if (props.currentMode === 'ALL') return columnKey !== 'ALL'
  if (props.currentMode === 'Weekly') return columnKey === 'ALL'
  return false
}

const isStageAvailable = (stageKey: string, columnKey: string) => {
  if (columnKey === 'ALL') return true

  // 从 API 缓存中检查关卡是否在该时间维度可用
  const cachedOptions = getCachedStageOptions(columnKey as TimeKey)
  const isInCache = cachedOptions.some(option => option.value === stageKey)

  if (isInCache) {
    return true
  }

  // 自定义关卡在所有时间段都可用
  return Object.values(coordinator.planData.customStageDefinitions).includes(stageKey)
}

// 计算已启用关卡数量
const getEnabledStageCount = (timeKey: string): number => {
  const config = coordinator.planData.timeConfigs[timeKey as TimeKey]
  if (!config) return 0

  return Object.values(config.stages).filter(stage => stage && stage !== '-').length
}

const isSwitchDisabled = (columnKey: string, record: any) => {
  const enabledCount = getEnabledStageCount(columnKey)
  const isCurrentlyEnabled = record[columnKey]

  // 如果已经有4个关卡且当前关卡未启用，则禁用
  if (enabledCount >= 4 && !isCurrentlyEnabled) {
    return true
  }

  // 对于自定义关卡，检查是否有有效名称
  const isCustomStageKey = Object.values(coordinator.planData.customStageDefinitions).includes(
    record.key
  )
  return isCustomStageKey && !record.key?.trim()
}

// 判断是否为自定义关卡
const isCustomStage = (stageName: string): boolean => {
  if (!stageName || stageName === '-') return false
  return Object.values(coordinator.planData.customStageDefinitions).includes(stageName)
}

// 关卡颜色映射
const STAGE_COLOR_MAP = {
  '当前/上次': 'blue',
  '龙门币-6/5': 'blue',
  '红票-5': 'volcano',
  '技能-5': 'cyan',
  '经验-6/5': 'gold',
  '碳-5': 'default',
} as const

const getStageTagColor = (taskName: string, isCustom?: boolean) => {
  if (isCustom) return 'purple'
  return STAGE_COLOR_MAP[taskName as keyof typeof STAGE_COLOR_MAP] || 'default'
}

// TIME_KEYS 常量用于简化视图批量操作
const TIME_KEYS: TimeKey[] = [
  'ALL',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

const enableAllStages = async (stageKey: string) => {
  for (const timeKey of TIME_KEYS) {
    if (isStageAvailable(stageKey, timeKey)) {
      const enabledCount = getEnabledStageCount(timeKey)
      if (enabledCount < 4) {
        coordinator.toggleStage(stageKey, timeKey, true)
      }
    }
  }
  // 保存整个时间配置
  const planConfig = coordinator.toApiData()
  for (const timeKey of TIME_KEYS) {
    const timeConfig = planConfig[timeKey]
    if (timeConfig) {
      await props.handlePlanChange(timeKey, timeConfig)
    }
  }
}

const disableAllStages = async (stageKey: string) => {
  for (const timeKey of TIME_KEYS) {
    coordinator.toggleStage(stageKey, timeKey, false)
  }
  // 保存整个时间配置
  const planConfig = coordinator.toApiData()
  for (const timeKey of TIME_KEYS) {
    const timeConfig = planConfig[timeKey]
    if (timeConfig) {
      await props.handlePlanChange(timeKey, timeConfig)
    }
  }
}

// 处理关卡切换 - 直接保存修改的字段
const handleStageToggle = async (stageKey: string, timeKey: TimeKey, enabled: boolean) => {
  coordinator.toggleStage(stageKey, timeKey, enabled)

  // 获取当前时间配置并保存
  const planConfig = coordinator.toApiData()
  const timeConfig = planConfig[timeKey]
  if (timeConfig) {
    await props.handlePlanChange(timeKey, timeConfig)
  }
}

// 监听 planId 变化
watch(
  () => props.planId,
  newPlanId => {
    if (newPlanId) {
      coordinator.updatePlanId(newPlanId)
    }
  },
  { immediate: true }
)

// 监听外部数据变化 - 这是数据的唯一来源
watch(
  () => props.tableData,
  async newData => {
    if (newData) {
      // 检查是否是初始加载
      const isInitialLoad = (newData as any)._isInitialLoad === true

      // 清理标记后传递给协调器
      const cleanData = { ...newData }
      delete (cleanData as any)._isInitialLoad

      // 如果是首次加载，确保先完成关卡选项的预加载，避免将标准关卡误判为自定义关卡
      if (isInitialLoad) {
        try {
          await preloadAllStageOptions()
        } catch (e) {
          // 预加载失败时降级为不阻塞——仍然尝试加载配置
          // 错误已由 preloadAllStageOptions 内部记录
        }
      }

      // 从后端数据加载到协调器
      coordinator.fromApiData(cleanData, isInitialLoad)
      // 同步到临时输入框
      tempCustomStages.value = { ...coordinator.planData.customStageDefinitions }
    }
  },
  { immediate: true }
)

// 监听协调器中的自定义关卡定义变化，同步到临时输入框
watch(
  () => coordinator.planData.customStageDefinitions,
  newDefinitions => {
    tempCustomStages.value = { ...newDefinitions }
    // 触发下拉框选项刷新
    customStageVersion.value++
  },
  { deep: true }
)

// 组件挂载时预加载关卡选项
onMounted(async () => {
  await preloadAllStageOptions()
})
</script>

<style scoped>
/* 复用原有样式 */
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

.config-input-number input {
  text-align: center;
}

.config-input-number :deep(.ant-input-number-input) {
  text-align: center;
}

.config-input-number :deep(.ant-input-number-handler-wrap) {
  display: none;
}

.config-select :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

.config-select :deep(.ant-select-selection-item),
.config-select :deep(.ant-select-selection-placeholder) {
  width: 100%;
  text-align: center;
  margin-inline-start: 0 !important;
}

/* 自定义关卡样式 - 与表格风格保持一致 */
.custom-stage-section {
  padding: 16px 20px;
  border-radius: 6px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
  min-height: auto;
  height: auto;
}

/* 紧凑的表单项样式 */
.compact-form-item {
  margin-bottom: 0 !important;
}

.compact-form-item :deep(.ant-form-item-label) {
  padding-bottom: 4px;
  line-height: 1.2;
}

.compact-form-item :deep(.ant-form-item-control) {
  line-height: 1.2;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.modern-input {
  border-radius: 4px;
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  transition: all 0.2s ease;
}

.modern-input:hover {
  border-color: var(--ant-color-primary-hover);
}

.modern-input:focus,
.modern-input.ant-input-focused {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

.task-tag {
  margin: 0;
}

:deep(.config-table .ant-table-tbody > tr > td) {
  text-align: center;
}

/* 自定义关卡特殊样式 - 只有颜色区分 */
.custom-stage-selected :deep(.ant-select-selection-item) {
  color: var(--ant-color-primary) !important;
  font-weight: 500;
}

.custom-stage-tag {
  font-weight: 500;
}

/* 下拉选项中的自定义关卡样式 */
:deep(.ant-select-item-option.custom-stage-option .ant-select-item-option-content) {
  color: var(--ant-color-primary) !important;
  font-weight: 500;
}
</style>
