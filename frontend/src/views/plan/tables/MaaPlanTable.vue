<template>
  <div>
    <!-- 自定义关卡设置区域 -->
    <a-card size="small" style="margin-bottom: 16px">
      <a-space wrap :size="[16, 8]">
        <div v-for="i in 4" :key="i" class="custom-stage-input-group">
          <span style="white-space: nowrap">自定义关卡 {{ i }}</span>
          <a-input
            v-model:value="tempCustomStages[`custom_stage_${i}` as keyof typeof tempCustomStages]"
            placeholder="输入关卡名称"
            size="small"
            style="width: 120px"
            :maxlength="50"
            allowClear
            @pressEnter="saveCustomStage(i as 1 | 2 | 3 | 4)"
          />
          <a-button
            size="small"
            type="primary"
            @click="saveCustomStage(i as 1 | 2 | 3 | 4)"
            :disabled="!hasCustomStageChanged(i as 1 | 2 | 3 | 4)"
          >
            保存
          </a-button>
        </div>
      </a-space>
    </a-card>

    <!-- 配置视图 -->
    <div v-show="viewMode === 'config'" class="config-table-wrapper">
      <a-table
        :key="`config-table-${currentMode}`"
        :columns="configColumns"
        :data-source="coordinator.configViewData.value"
        :pagination="false"
        :class="['config-table', `mode-${currentMode}`]"
        size="middle"
        :bordered="true"
        :scroll="{ x: 'max-content' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'taskName'">
            {{ record.taskName }}
          </template>

          <template v-else-if="record.taskName === '吃理智药'">
            <a-input-number
              :value="(record as any)[column.key]"
              @update:value="updateConfigValue(record.key, column.key as TimeKey, $event)"
              size="small"
              :min="0"
              :max="999"
              class="config-input-number"
              :controls="false"
              :bordered="false"
              :disabled="isColumnDisabled(column.key as string)"
            />
          </template>

          <template v-else>
            <a-select
              :value="(record as any)[column.key]"
              @update:value="updateConfigValue(record.key, column.key as TimeKey, $event)"
              size="small"
              :class="[
                'config-select',
                {
                  'custom-stage-selected': isCustomStage((record as any)[column.key]),
                },
              ]"
              allow-clear
              :bordered="false"
              :disabled="isColumnDisabled(column.key as string)"
            >
              <a-select-option
                v-for="option in getSelectOptions(
                  column.key as string,
                  record.taskName,
                  (record as any)[column.key] as string
                )"
                :key="option.value"
                :value="option.value"
                :disabled="option.disabled"
                :class="{ 'custom-stage-option': isCustomStage(option.value) }"
              >
                <span
                  :style="{
                    color: isCustomStage(option.value) ? 'var(--ant-color-primary)' : undefined,
                    fontWeight: isCustomStage(option.value) ? '500' : 'normal',
                  }"
                >
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
      <a-table
        :key="`simple-table-${currentMode}`"
        :columns="simpleColumns"
        :data-source="coordinator.simpleViewData.value"
        :pagination="false"
        class="simple-table"
        size="small"
        :bordered="true"
        :scroll="{ x: 'max-content' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'globalControl'">
            <a-space>
              <a-button ghost size="small" type="primary" @click="enableAllStages(record.key)"
                >开</a-button
              >
              <a-button size="small" danger @click="disableAllStages(record.key)">关</a-button>
            </a-space>
          </template>

          <template v-else-if="column.key === 'taskName'">
            <a-tag
              :color="getStageTagColor(record.taskName, record.isCustom)"
              class="task-tag"
              :class="{ 'custom-stage-tag': record.isCustom }"
            >
              {{ record.taskName }}
            </a-tag>
          </template>

          <template v-else>
            <a-switch
              v-if="isStageAvailable(record.key, column.key as string)"
              :checked="record[column.key]"
              @change="handleStageToggle(record.key, column.key as TimeKey, $event)"
              :disabled="isSwitchDisabled(column.key as string, record)"
            />
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  usePlanDataCoordinator,
  TIME_KEYS,
  STAGE_DAILY_INFO,
  type TimeKey,
} from '@/composables/usePlanDataCoordinator'

interface Props {
  tableData: Record<string, any> | null
  currentMode: 'ALL' | 'Weekly'
  viewMode: 'config' | 'simple'
  planId?: string
}

interface Emits {
  (e: 'update-table-data', value: Record<string, any>): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 使用数据协调器 - 单一数据源
const coordinator = usePlanDataCoordinator()

// 临时自定义关卡输入
const tempCustomStages = ref({
  custom_stage_1: '',
  custom_stage_2: '',
  custom_stage_3: '',
  custom_stage_4: '',
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

// 更新配置数据
const updateConfigValue = (rowKey: string, timeKey: TimeKey, value: any) => {
  coordinator.updateConfig(timeKey, rowKey, value)
  emitUpdate()
}

// 自定义关卡管理
const hasCustomStageChanged = (index: 1 | 2 | 3 | 4): boolean => {
  const key = `custom_stage_${index}` as keyof typeof tempCustomStages.value
  return tempCustomStages.value[key] !== coordinator.planData.customStageDefinitions[key]
}

const saveCustomStage = (index: 1 | 2 | 3 | 4) => {
  const key = `custom_stage_${index}` as keyof typeof tempCustomStages.value
  const newValue = tempCustomStages.value[key].trim()

  // 更新自定义关卡定义
  coordinator.updateCustomStageDefinition(index, newValue)
  
  // 保存到后端
  emitUpdate()

  message.success(newValue ? `自定义关卡-${index} 已保存` : `自定义关卡-${index} 已删除`)
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

  // 关卡选择选项
  const dayNumber = getDayNumber(columnKey)
  const baseOptions: SelectOption[] = (
    dayNumber === 0
      ? STAGE_DAILY_INFO
      : STAGE_DAILY_INFO.filter(stage => stage.days.includes(dayNumber))
  ).map(stage => ({ label: stage.text, value: stage.value }))

  // 添加自定义关卡选项
  Object.values(coordinator.planData.customStageDefinitions).forEach(stageName => {
    if (stageName?.trim()) {
      baseOptions.push({ label: stageName, value: stageName })
    }
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

  const stage = STAGE_DAILY_INFO.find(s => s.value === stageKey)
  if (stage) {
    const dayNumber = getDayNumber(columnKey)
    return stage.days.includes(dayNumber)
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

const enableAllStages = (stageKey: string) => {
  TIME_KEYS.forEach(timeKey => {
    if (isStageAvailable(stageKey, timeKey)) {
      const enabledCount = getEnabledStageCount(timeKey)
      if (enabledCount < 4) {
        coordinator.toggleStage(stageKey, timeKey, true)
      }
    }
  })
  emitUpdate()
}

const disableAllStages = (stageKey: string) => {
  TIME_KEYS.forEach(timeKey => {
    coordinator.toggleStage(stageKey, timeKey, false)
  })
  emitUpdate()
}

// 处理关卡切换
const handleStageToggle = (stageKey: string, timeKey: TimeKey, enabled: boolean) => {
  coordinator.toggleStage(stageKey, timeKey, enabled)
  emitUpdate()
}

// 数据更新通知
const emitUpdate = () => {
  emit('update-table-data', coordinator.toApiData())
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
  newData => {
    if (newData) {
      // 检查是否是初始加载
      const isInitialLoad = (newData as any)._isInitialLoad === true
      
      // 清理标记后传递给协调器
      const cleanData = { ...newData }
      delete (cleanData as any)._isInitialLoad
      
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
  },
  { deep: true }
)
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

.custom-stage-input-group {
  display: flex;
  align-items: center;
  gap: 8px;
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
