<template>
  <div>
    <!-- 配置视图 -->
    <div v-show="viewMode === 'config'" class="config-table-wrapper">
      <a-table
        :key="`config-table-${currentMode}-${columnKeys.length}`"
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
              size="small"
              :min="0"
              :max="9999"
              class="config-input-number"
              :controls="false"
              :bordered="false"
              :disabled="isColumnDisabled(column.key as string)"
              @update:value="updateConfigValue(record.key, column.key as string, $event)"
            />
          </template>

          <template v-else>
            <a-select
              :value="(record as any)[column.key]"
              size="small"
              :class="[
                'config-select',
                {
                  'custom-stage-selected': isCustomStage((record as any)[column.key]),
                },
              ]"
              :allow-clear="false"
              :bordered="false"
              :disabled="isColumnDisabled(column.key as string)"
              @update:value="updateConfigValue(record.key, column.key as string, $event)"
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
        :key="`simple-table-${currentMode}-${columnKeys.length}`"
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
              <a-button ghost size="small" type="primary" @click="enableAllStages(record.key)">{{
                t('plan.table.on')
              }}</a-button>
              <a-button size="small" danger @click="disableAllStages(record.key)">{{
                t('plan.table.off')
              }}</a-button>
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
              :disabled="isSwitchDisabled(column.key as string, record)"
              @change="handleStageToggle(record.key, column.key as string, $event)"
            />
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
              <a-tooltip :title="t('plan.table.customStageTip')">
                <span class="form-label">
                  {{ t('plan.table.customStage', { n: i }) }}
                  <QuestionCircleOutlined class="help-icon" />
                </span>
              </a-tooltip>
            </template>
            <a-input
              v-model:value="tempCustomStages[`custom_stage_${i}` as keyof typeof tempCustomStages]"
              :placeholder="t('plan.table.stagePlaceholder')"
              :maxlength="50"
              allow-clear
              size="large"
              @input="onCustomStageInput(i as 1 | 2 | 3 | 4)"
              @blur="onCustomStageBlurOrEnter(i as 1 | 2 | 3 | 4)"
              @press-enter="onCustomStageBlurOrEnter(i as 1 | 2 | 3 | 4)"
            />
          </a-form-item>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { savePlanDayBatch } from '../savePlanDayBatch'
import { useI18n } from 'vue-i18n'
import { ref, watch, computed } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import {
  usePlanDataCoordinator,
  preloadAllStageOptions,
  getCachedStageOptions,
} from '@/composables/usePlanDataCoordinator'
import {
  mergePlanData,
  planAllDayKeys,
  planColumnKeys,
  planColumnPath,
  planColumnGroup,
  planDayLabel,
  readPlanColumn,
  type PlanMode,
} from '@/utils/planDays'

const { t } = useI18n()

interface Props {
  tableData: Record<string, any> | null
  currentMode: PlanMode
  viewMode: 'config' | 'simple'
  planId?: string
  handlePlanChange: import('@/utils/planTypeRegistry').PlanChangeHandler
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

// 记录最近一次从后端加载或保存成功的自定义关卡。
// 输入事件会为了实时刷新下拉选项提前修改 coordinator，
// 因此保存判断必须和这份快照比较，不能直接读取当前定义。
const savedCustomStages = ref({
  custom_stage_1: '',
  custom_stage_2: '',
  custom_stage_3: '',
  custom_stage_4: '',
})

// 用于触发下拉框选项刷新的响应式变量
const customStageVersion = ref(0)
let tableDataLoadVersion = 0

// 计算属性：获取当前的自定义关卡列表（用于响应式更新）
const currentCustomStages = computed(() => {
  // 访问 customStageVersion 以触发响应式更新

  customStageVersion.value

  return Object.values(coordinator.planData.customStageDefinitions).filter(stageName =>
    stageName?.trim()
  )
})

/** 列键：ALL 加当天的天键；周计划是星期名，多天轮换是 "1"~"N" */
const columnKeys = computed(() =>
  planColumnKeys(props.currentMode, props.tableData?.Info?.RotateDays)
)

const columnTitle = (key: string) =>
  key === 'ALL' ? t('plan.week.ALL') : t(planDayLabel(key).key, planDayLabel(key).params)

// 配置视图列定义
const configColumns = computed(() => [
  {
    title: t('plan.table.field'),
    dataIndex: 'taskName',
    key: 'taskName',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  ...columnKeys.value.map(key => ({
    title: columnTitle(key),
    dataIndex: key,
    key,
    width: 120,
    align: 'center',
  })),
])

// 简化视图列定义
const simpleColumns = computed(() => [
  {
    title: t('plan.table.globalControl'),
    key: 'globalControl',
    width: 75,
    fixed: 'left',
    align: 'center',
  },
  {
    title: t('plan.table.stage'),
    dataIndex: 'taskName',
    key: 'taskName',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  ...configColumns.value.filter(col => col.key !== 'taskName'),
])

/**
 * 整份天配置直接写入对应配置分组。
 * 契约里的 planColumnPath 拼的是「某一天的某个字段」，整份配置没有字段名，所以在外面拼这一段。
 */
const dayConfigPath = planColumnGroup

// 更新配置数据 - 直接调用父组件的保存函数
const updateConfigValue = async (rowKey: string, timeKey: string, value: any) => {
  // 更新本地状态
  coordinator.updateConfig(timeKey, rowKey, value)

  // 构建后端 API 路径，例如 "ALL.Stage" 或 "Monday.MedicineNumb"
  const apiPath = planColumnPath(timeKey, rowKey)
  await props.handlePlanChange(apiPath, value)
}

// 自定义关卡保存 - 失去焦点或按回车时保存
const saveCustomStage = async (index: 1 | 2 | 3 | 4) => {
  const key = `custom_stage_${index}` as keyof typeof tempCustomStages.value
  const newValue = tempCustomStages.value[key].trim()
  const oldValue = savedCustomStages.value[key].trim()

  // 如果值没有变化，不需要保存
  if (newValue === oldValue) {
    return
  }

  // 更新自定义关卡定义
  coordinator.updateCustomStageDefinition(index, newValue)

  // 改名要覆盖所有引用这一关卡的槽位：协调器只持有当前显示的那几天（轮换模式下就是
  // 第 1~N 天），所以拿后端返回的完整配置打底，再用协调器里的最新编辑值覆盖一遍。
  const planConfig = mergePlanData(props.tableData, coordinator.toApiData())
  const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3']
  const pending: { path: string; config: Record<string, any> }[] = []

  for (const timeKey of planAllDayKeys(planConfig)) {
    const timeConfig = readPlanColumn(planConfig, timeKey) as Record<string, any> | undefined
    if (!timeConfig) {
      continue
    }

    const before = stageFields.map(field => timeConfig[field])
    for (const field of stageFields) {
      if (timeConfig[field] === oldValue && oldValue !== '') {
        // 更新为新值
        timeConfig[field] = newValue
      }
    }

    // 只发真的改到的槽位：轮换 31 天时一共三十多个槽位，多数用不到这个自定义关卡
    if (stageFields.some((field, position) => timeConfig[field] !== before[position])) {
      pending.push({ path: dayConfigPath(timeKey), config: timeConfig })
    }
  }

  const allSaved = await savePlanDayBatch(props.handlePlanChange, pending, props.viewMode, false)

  if (allSaved) {
    savedCustomStages.value = { ...coordinator.planData.customStageDefinitions }
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

// 连战次数选项。label 里的“不切换”随语言变，所以整表是 computed
const SERIES_OPTIONS = computed<SelectOption[]>(() => [
  { label: 'AUTO', value: '0' },
  { label: '1', value: '1' },
  { label: '2', value: '2' },
  { label: '3', value: '3' },
  { label: '4', value: '4' },
  { label: '5', value: '5' },
  { label: '6', value: '6' },
  { label: t('plan.table.noSwitch'), value: '-1' },
])

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
    return SERIES_OPTIONS.value
  }

  // 关卡选择选项 - 从 API 缓存获取
  const cachedOptions = getCachedStageOptions(columnKey)
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
        ? t('plan.table.usedSuffix', { label: option.label })
        : option.label,
  }))
}

// 获取已使用的关卡
const getUsedStagesInColumn = (columnKey: string): string[] => {
  const config = coordinator.planData.timeConfigs[columnKey]
  if (!config) return []

  return Object.values(config.stages).filter(stage => stage && stage !== '-')
}

// 工具函数
const isColumnDisabled = (columnKey: string): boolean => {
  // ALL 模式只打 ALL 这一列；周计划与多天轮换都按当天取值，ALL 列不参与，禁用免得改了个不生效的值
  if (props.currentMode === 'ALL') return columnKey !== 'ALL'
  return columnKey === 'ALL'
}

const isStageAvailable = (stageKey: string, columnKey: string) => {
  if (columnKey === 'ALL') return true

  // 从 API 缓存中检查关卡是否在该时间维度可用
  const cachedOptions = getCachedStageOptions(columnKey)
  const isInCache = cachedOptions.some(option => option.value === stageKey)

  if (isInCache) {
    return true
  }

  // 自定义关卡在所有时间段都可用
  return Object.values(coordinator.planData.customStageDefinitions).includes(stageKey)
}

// 计算已启用关卡数量
const getEnabledStageCount = (timeKey: string): number => {
  const config = coordinator.planData.timeConfigs[timeKey]
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

// 批量操作与整份保存都按当前的天键走：周计划是七天，多天轮换是前 N 天，两种都含 ALL

const enableAllStages = async (stageKey: string) => {
  for (const timeKey of columnKeys.value) {
    if (isStageAvailable(stageKey, timeKey)) {
      const enabledCount = getEnabledStageCount(timeKey)
      if (enabledCount < 4) {
        coordinator.toggleStage(stageKey, timeKey, true)
      }
    }
  }
  await saveAllTimeConfigs()
}

const disableAllStages = async (stageKey: string) => {
  for (const timeKey of columnKeys.value) {
    coordinator.toggleStage(stageKey, timeKey, false)
  }
  await saveAllTimeConfigs()
}

// 逐个天保存整份天配置，只在最后一次回读，避免每个天各带一次 get
const saveAllTimeConfigs = async () => {
  const planConfig = coordinator.toApiData()
  const timeKeys = columnKeys.value.filter(timeKey => readPlanColumn(planConfig, timeKey))
  await savePlanDayBatch(
    props.handlePlanChange,
    timeKeys.map(timeKey => ({
      path: dayConfigPath(timeKey),
      config: readPlanColumn(planConfig, timeKey),
    })),
    props.viewMode
  )
}

// 处理关卡切换 - 直接保存修改的字段
const handleStageToggle = async (stageKey: string, timeKey: string, enabled: boolean) => {
  coordinator.toggleStage(stageKey, timeKey, enabled)

  // 获取当前天的整份配置并保存
  const planConfig = coordinator.toApiData()
  const timeConfig = readPlanColumn(planConfig, timeKey)
  if (timeConfig) {
    await props.handlePlanChange(dayConfigPath(timeKey), timeConfig)
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

// 监听外部数据变化 - 这是数据的唯一来源。
// 列键同时取决于模式与轮换天数，所以这三个来源任一变化都要把本地数据重新解析一遍。
watch(
  () => [props.tableData, props.currentMode, props.tableData?.Info?.RotateDays] as const,
  async ([newData]) => {
    const loadVersion = ++tableDataLoadVersion
    if (newData) {
      // 检查是否是初始加载
      const isInitialLoad = (newData as any)._isInitialLoad === true

      // 清理标记后传递给协调器
      const cleanData = { ...newData }
      delete (cleanData as any)._isInitialLoad

      // 先渲染后端已有配置，关卡资源在后台预加载。
      if (isInitialLoad) {
        coordinator.fromApiData(cleanData, false, false)
        try {
          await preloadAllStageOptions(columnKeys.value)
        } catch {
          // 预加载失败时保留已渲染的配置
          return
        }
        if (loadVersion !== tableDataLoadVersion) return
        coordinator.fromApiData(cleanData, true)
        tempCustomStages.value = { ...coordinator.planData.customStageDefinitions }
        savedCustomStages.value = { ...coordinator.planData.customStageDefinitions }
        return
      }

      // 从后端数据加载到协调器
      coordinator.fromApiData(cleanData)
      // 切模式或改轮换天数之后，当前列要的池可能还没拉过（例如从轮换切回周计划要七天池），
      // 这里补一轮；已经齐全的池会被跳过，不重复请求。
      void preloadAllStageOptions(columnKeys.value).catch(() => undefined)
      // 同步到临时输入框
      tempCustomStages.value = { ...coordinator.planData.customStageDefinitions }
      // 非初始刷新可能保留了 fromApiData(false) 续住的未保存输入，
      // 不能把它们当作后端确认值写入 savedCustomStages。
      if (isInitialLoad) {
        savedCustomStages.value = { ...coordinator.planData.customStageDefinitions }
      }
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
