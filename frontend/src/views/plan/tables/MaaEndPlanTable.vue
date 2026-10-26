<template>
  <div>
    <div v-show="viewMode === 'config'" class="config-table-wrapper">
      <a-table
        :key="`maaend-config-table-${currentMode}-${columnKeys.length}`"
        :columns="configColumns"
        :data-source="configRows"
        :pagination="false"
        class="config-table"
        size="middle"
        :bordered="true"
        :scroll="{ x: 'max-content' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'fieldName'">
            {{ record.fieldName }}
          </template>

          <template v-else>
            <a-select
              v-if="record.rowKey === 'SanityTaskType'"
              :value="record[column.key]"
              size="small"
              class="config-select"
              :bordered="false"
              :disabled="isColumnDisabled(column.key)"
              @update:value="handleSanityTaskTypeChange(column.key, $event)"
            >
              <a-select-option
                v-for="option in sanityTaskTypeOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </a-select-option>
            </a-select>

            <a-select
              v-else-if="record.rowKey === 'EssenceMenu'"
              :value="record[column.key]"
              size="small"
              class="config-select"
              :bordered="false"
              :options="essenceMenuOptions"
              :disabled="
                isColumnDisabled(column.key) ||
                getDayConfig(column.key).SanityTaskType !== 'Essence'
              "
              @update:value="handleEssenceMenuChange(column.key, $event)"
            />

            <a-select
              v-else-if="record.rowKey === 'CurrentTask'"
              :value="record[column.key]"
              size="small"
              class="config-select"
              :bordered="false"
              :loading="isEssenceLocationLoading(column.key)"
              :disabled="isColumnDisabled(column.key)"
              :mode="isTargetEssenceMode(column.key) ? 'multiple' : undefined"
              @update:value="handleTaskChange(column.key, $event)"
            >
              <a-select-option
                v-for="option in getCurrentTaskOptions(column.key)"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </a-select-option>
            </a-select>

            <a-select
              v-else
              :value="record[column.key]"
              size="small"
              class="config-select"
              :bordered="false"
              :disabled="isColumnDisabled(column.key) || !isRewardGroupEnabledForTime(column.key)"
              @update:value="handleRewardChange(column.key, $event)"
            >
              <a-select-option
                v-for="option in REWARD_OPTIONS"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </a-select-option>
            </a-select>
          </template>
        </template>
      </a-table>
    </div>

    <div v-show="viewMode === 'simple'" class="simple-table-wrapper">
      <a-table
        :key="`maaend-simple-table-${currentMode}-${columnKeys.length}`"
        :columns="simpleColumns"
        :data-source="simpleRows"
        :pagination="false"
        class="simple-table"
        size="middle"
        :bordered="true"
        :scroll="{ x: 'max-content' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'timeLabel'">
            {{ record.timeLabel }}
          </template>

          <a-select
            v-else-if="column.key === 'SanityTaskType'"
            :value="record.SanityTaskType"
            size="small"
            class="config-select"
            :bordered="false"
            :disabled="isColumnDisabled(record.key)"
            @update:value="handleSanityTaskTypeChange(record.key, $event)"
          >
            <a-select-option
              v-for="option in sanityTaskTypeOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </a-select-option>
          </a-select>

          <a-select
            v-else-if="column.key === 'EssenceMenu'"
            :value="record.EssenceMenu"
            size="small"
            class="config-select"
            :bordered="false"
            :options="essenceMenuOptions"
            :disabled="isColumnDisabled(record.key) || record.SanityTaskType !== 'Essence'"
            @update:value="handleEssenceMenuChange(record.key, $event)"
          />

          <a-select
            v-else-if="column.key === 'CurrentTask'"
            :value="record.CurrentTask"
            size="small"
            class="config-select"
            :bordered="false"
            :loading="isEssenceLocationLoading(record.key)"
            :disabled="isColumnDisabled(record.key)"
            :mode="isTargetEssenceMode(record.key) ? 'multiple' : undefined"
            @update:value="handleTaskChange(record.key, $event)"
          >
            <a-select-option
              v-for="option in getCurrentTaskOptions(record.key)"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </a-select-option>
          </a-select>

          <a-select
            v-else
            :value="record.RewardsSetOption"
            size="small"
            class="config-select"
            :bordered="false"
            :disabled="isColumnDisabled(record.key) || !isRewardGroupEnabledForTime(record.key)"
            @update:value="handleRewardChange(record.key, $event)"
          >
            <a-select-option
              v-for="option in REWARD_OPTIONS"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </a-select-option>
          </a-select>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { useMaaEndPlanOptions } from './useMaaEndPlanOptions'
import {
  AUTO_ESSENCE_MENU_OPTIONS,
  PROTOCOL_SPACE_TASK_FIELD_MAP,
  PROTOCOL_SPACE_TASK_OPTIONS_MAP,
  REWARD_OPTIONS,
  SANITY_TASK_TYPE_OPTIONS,
  getCurrentTaskValue,
  getEssenceTargetWeaponOptions,
  isProtocolSpaceRewardEnabled,
  maaEndPlanKeyToSanityConfig,
  normalizeMaaEndPlanKey,
  normalizeMaaEndSanityConfig,
  type CurrentTaskValue,
  type MaaEndSanityConfig,
  type ProtocolSpaceTab,
  type RewardSetOption,
  type SanityTaskType,
} from '@/utils/maaEndProtocolSpace'
import {
  planColumnKeys,
  planColumnPath,
  planDayLabel,
  readPlanColumn,
  type PlanMode,
} from '@/utils/planDays'
import type { PlanChangeHandler } from '@/utils/planTypeRegistry'

const { t } = useI18n()

interface Props {
  tableData: Record<string, any> | null
  currentMode: PlanMode
  viewMode: 'config' | 'simple'
  planId?: string
  handlePlanChange: PlanChangeHandler
}

const props = defineProps<Props>()

const localTableData = ref<Record<string, MaaEndSanityConfig>>({})
const {
  crisisDrillsOptions,
  essenceLocationOptions,
  essenceMenuOptions,
  essenceTargetWeaponGroups,
  essenceOptionsLoading,
  essenceOptionsLoaded,
} = useMaaEndPlanOptions()

const sanityTaskTypeOptions = computed(() =>
  SANITY_TASK_TYPE_OPTIONS.filter(
    option =>
      option.value !== 'Essence' ||
      !essenceOptionsLoaded.value ||
      essenceLocationOptions.value.length > 0 ||
      essenceTargetWeaponGroups.value.length > 0 ||
      Object.values(localTableData.value).some(config => config?.SanityTaskType === 'Essence')
  )
)

/** 列键：ALL 加当天的天键；周计划是星期名，多天轮换是 "1"~"N" */
const columnKeys = computed(() =>
  planColumnKeys(props.currentMode, props.tableData?.Info?.RotateDays)
)

const columnTitle = (key: string) =>
  key === 'ALL' ? t('plan.week.ALL') : t(planDayLabel(key).key, planDayLabel(key).params)

const syncLocalTableData = (tableData: Record<string, any> | null) => {
  localTableData.value = Object.fromEntries(
    columnKeys.value.map(key => [key, maaEndPlanKeyToSanityConfig(readPlanColumn(tableData, key))])
  ) as Record<string, MaaEndSanityConfig>
}

// 列键同时取决于模式与轮换天数，任何一个变了都要重读一遍
watch(
  () => [props.tableData, props.currentMode, props.tableData?.Info?.RotateDays] as const,
  () => syncLocalTableData(props.tableData),
  { immediate: true }
)

const configColumns = computed(() => [
  {
    title: t('plan.table.field'),
    dataIndex: 'fieldName',
    key: 'fieldName',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  ...columnKeys.value.map(key => ({
    title: columnTitle(key),
    dataIndex: key,
    key,
    width: 160,
    align: 'center' as const,
  })),
])

const simpleColumns = computed(() => [
  {
    title: t('plan.table.time'),
    dataIndex: 'timeLabel',
    key: 'timeLabel',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  {
    title: t('plan.table.taskType'),
    dataIndex: 'SanityTaskType',
    key: 'SanityTaskType',
    width: 140,
    align: 'center',
  },
  {
    title: '基质模式',
    dataIndex: 'EssenceMenu',
    key: 'EssenceMenu',
    width: 140,
    align: 'center',
  },
  {
    title: t('plan.table.currentTask'),
    dataIndex: 'CurrentTask',
    key: 'CurrentTask',
    width: 220,
    align: 'center',
  },
  {
    title: t('plan.table.rewardsSet'),
    dataIndex: 'RewardsSetOption',
    key: 'RewardsSetOption',
    width: 160,
    align: 'center',
  },
])

const isColumnDisabled = (key: string) => {
  if (props.currentMode === 'ALL') return key !== 'ALL'
  return key === 'ALL'
}

const getDayConfig = (key: string): MaaEndSanityConfig =>
  normalizeMaaEndSanityConfig(localTableData.value?.[key])

const getCurrentTaskOptions = (key: string) => {
  const dayConfig = getDayConfig(key)
  if (dayConfig.SanityTaskType === 'Essence') {
    if (dayConfig.AutoEssenceMenu === 'Target') {
      return getEssenceTargetWeaponOptions(
        essenceTargetWeaponGroups.value,
        dayConfig.AutoEssenceTargetWeapons
      )
    }
    const options = [...essenceLocationOptions.value]
    if (
      dayConfig.AutoEssenceSpecifiedLocation &&
      !options.some(option => option.value === dayConfig.AutoEssenceSpecifiedLocation)
    ) {
      options.unshift({
        label: dayConfig.AutoEssenceSpecifiedLocation,
        value: dayConfig.AutoEssenceSpecifiedLocation,
      })
    }
    return options
  }
  if (dayConfig.SanityTaskType === 'CrisisDrills') {
    const options = [...crisisDrillsOptions.value]
    if (!options.some(option => option.value === dayConfig.CrisisDrills)) {
      options.unshift({ label: dayConfig.CrisisDrills, value: dayConfig.CrisisDrills })
    }
    return options
  }
  return PROTOCOL_SPACE_TASK_OPTIONS_MAP[dayConfig.SanityTaskType as ProtocolSpaceTab]
}

const isTargetEssenceMode = (key: string) => {
  const dayConfig = getDayConfig(key)
  return dayConfig.SanityTaskType === 'Essence' && dayConfig.AutoEssenceMenu === 'Target'
}

const getEssenceMenu = (key: string) => getDayConfig(key).AutoEssenceMenu

const isEssenceLocationLoading = (key: string) =>
  essenceOptionsLoading.value && getDayConfig(key).SanityTaskType === 'Essence'

const isRewardGroupEnabledForTime = (key: string) => {
  const dayConfig = getDayConfig(key)
  if (dayConfig.SanityTaskType === 'Essence') return false
  return isProtocolSpaceRewardEnabled(dayConfig)
}

const configRows = computed(() => [
  {
    rowKey: 'SanityTaskType',
    fieldName: t('plan.table.sanityTask'),
    ...Object.fromEntries(columnKeys.value.map(key => [key, getDayConfig(key).SanityTaskType])),
  },
  {
    rowKey: 'EssenceMenu',
    fieldName: '基质模式',
    ...Object.fromEntries(columnKeys.value.map(key => [key, getEssenceMenu(key)])),
  },
  {
    rowKey: 'CurrentTask',
    fieldName: t('plan.table.currentTask'),
    ...Object.fromEntries(
      columnKeys.value.map(key => [key, getCurrentTaskValue(getDayConfig(key))])
    ),
  },
  {
    rowKey: 'RewardsSetOption',
    fieldName: t('plan.table.rewardsSet'),
    ...Object.fromEntries(columnKeys.value.map(key => [key, getDayConfig(key).RewardsSetOption])),
  },
])

const simpleRows = computed(() => {
  const keys = props.currentMode === 'ALL' ? ['ALL'] : columnKeys.value.filter(key => key !== 'ALL')

  return keys.map(key => {
    const dayConfig = getDayConfig(key)
    return {
      key,
      timeLabel: columnTitle(key),
      SanityTaskType: dayConfig.SanityTaskType,
      CurrentTask: getCurrentTaskValue(dayConfig),
      EssenceMenu: dayConfig.AutoEssenceMenu,
      RewardsSetOption: dayConfig.RewardsSetOption,
    }
  })
})

const saveDayConfig = async (key: string, config: Partial<MaaEndSanityConfig>) => {
  const normalized = normalizeMaaEndSanityConfig(config)
  const previous = localTableData.value[key]

  localTableData.value = {
    ...localTableData.value,
    [key]: normalized,
  }

  const saved = await props.handlePlanChange(
    planColumnPath(key, 'Key'),
    normalizeMaaEndPlanKey(normalized),
    false
  )
  if (!saved) {
    localTableData.value = {
      ...localTableData.value,
      [key]: previous ?? normalizeMaaEndSanityConfig(),
    }
  }
}

const handleSanityTaskTypeChange = async (key: string, value: SanityTaskType) => {
  await saveDayConfig(key, {
    ...getDayConfig(key),
    SanityTaskType: value,
  })
}

const handleTaskChange = async (key: string, value: CurrentTaskValue) => {
  const currentConfig = getDayConfig(key)
  if (currentConfig.SanityTaskType === 'Essence') {
    if (currentConfig.AutoEssenceMenu === 'Target') {
      await saveDayConfig(key, {
        ...currentConfig,
        AutoEssenceTargetWeapons: Array.isArray(value) ? value : [],
      })
      return
    }
    await saveDayConfig(key, {
      ...currentConfig,
      AutoEssenceSpecifiedLocation: value as MaaEndSanityConfig['AutoEssenceSpecifiedLocation'],
    })
    return
  }

  await saveDayConfig(key, {
    ...currentConfig,
    [PROTOCOL_SPACE_TASK_FIELD_MAP[currentConfig.SanityTaskType as ProtocolSpaceTab]]:
      value as MaaEndSanityConfig['OperatorProgression'],
  })
}

const handleEssenceMenuChange = async (key: string, value: string) => {
  if (!AUTO_ESSENCE_MENU_OPTIONS.some(option => option.value === value)) return
  await saveDayConfig(key, {
    ...getDayConfig(key),
    AutoEssenceMenu: value as MaaEndSanityConfig['AutoEssenceMenu'],
  })
}

const handleRewardChange = async (key: string, value: RewardSetOption) => {
  await saveDayConfig(key, {
    ...getDayConfig(key),
    RewardsSetOption: value,
  })
}
</script>

<style scoped>
.config-table-wrapper,
.simple-table-wrapper {
  overflow: hidden;
}

.config-select {
  width: 100%;
}

.config-table :deep(.ant-table-cell),
.simple-table :deep(.ant-table-cell) {
  vertical-align: middle;
}

.config-table :deep(.ant-select-selector),
.simple-table :deep(.ant-select-selector) {
  min-height: 32px;
}
</style>
