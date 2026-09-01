<template>
  <div>
    <div v-show="viewMode === 'config'" class="config-table-wrapper">
      <a-table
        :key="`maaend-config-table-${currentMode}`"
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
              :disabled="isColumnDisabled(asTimeKey(column.key))"
              @update:value="handleSanityTaskTypeChange(asTimeKey(column.key), $event)"
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
              v-else-if="record.rowKey === 'CurrentTask'"
              :value="record[column.key]"
              size="small"
              class="config-select"
              :bordered="false"
              :loading="isEssenceLocationLoading(asTimeKey(column.key))"
              :disabled="isColumnDisabled(asTimeKey(column.key))"
              @update:value="handleTaskChange(asTimeKey(column.key), $event)"
            >
              <a-select-option
                v-for="option in getCurrentTaskOptions(asTimeKey(column.key))"
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
              :disabled="
                isColumnDisabled(asTimeKey(column.key)) ||
                !isRewardGroupEnabledForTime(asTimeKey(column.key))
              "
              @update:value="handleRewardChange(asTimeKey(column.key), $event)"
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
        :key="`maaend-simple-table-${currentMode}`"
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
            v-else-if="column.key === 'CurrentTask'"
            :value="record.CurrentTask"
            size="small"
            class="config-select"
            :bordered="false"
            :loading="isEssenceLocationLoading(record.key)"
            :disabled="isColumnDisabled(record.key)"
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
import { computed, onMounted, ref, watch } from 'vue'
import type { ComboBoxItem, MaaEndConfig } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import {
  MAAEND_PLAN_TIME_KEYS,
  MAAEND_PLAN_TIME_LABELS,
  PROTOCOL_SPACE_TASK_FIELD_MAP,
  PROTOCOL_SPACE_TASK_OPTIONS_MAP,
  REWARD_OPTIONS,
  SANITY_TASK_TYPE_OPTIONS,
  getCurrentTaskValue,
  isProtocolSpaceRewardEnabled,
  maaEndPlanKeyToSanityConfig,
  normalizeMaaEndPlanKey,
  normalizeMaaEndSanityConfig,
  type CurrentTaskValue,
  type MaaEndSanityConfig,
  type PlanTimeKey,
  type ProtocolSpaceTab,
  type RewardSetOption,
  type SanityTaskType,
} from '@/utils/maaEndProtocolSpace'
import type { PlanChangeHandler } from '@/utils/planTypeRegistry'

const { t } = useI18n()

interface Props {
  tableData: Record<string, any> | null
  currentMode: 'ALL' | 'Weekly'
  viewMode: 'config' | 'simple'
  planId?: string
  handlePlanChange: PlanChangeHandler
}

const props = defineProps<Props>()

const { getScripts, getMaaEndOptions } = useScriptApi()
const localTableData = ref<Partial<Record<PlanTimeKey, MaaEndSanityConfig>>>({})
const essenceLocationOptions = ref<ComboBoxItem[]>([])
const essenceOptionsLoading = ref(false)
const essenceOptionsLoaded = ref(false)

const sanityTaskTypeOptions = computed(() =>
  SANITY_TASK_TYPE_OPTIONS.filter(
    option =>
      option.value !== 'Essence' ||
      !essenceOptionsLoaded.value ||
      essenceLocationOptions.value.length > 0 ||
      Object.values(localTableData.value).some(config => config?.SanityTaskType === 'Essence')
  )
)

const loadEssenceLocationOptions = async () => {
  essenceOptionsLoading.value = true
  try {
    const scripts = await getScripts(false)
    const configuredMaaEndScripts = scripts.filter(script => {
      if (script.type !== 'MaaEnd') return false
      const config = script.config as MaaEndConfig
      return Boolean(config.Info?.Path?.trim())
    })
    const responses = await Promise.all(
      configuredMaaEndScripts.map(script => getMaaEndOptions(script.uid))
    )
    const optionsByValue = new Map<string, ComboBoxItem>()
    responses.forEach(response => {
      response?.essenceLocations.forEach(option => {
        if (option.value && !optionsByValue.has(option.value)) {
          optionsByValue.set(option.value, option)
        }
      })
    })
    essenceLocationOptions.value = [...optionsByValue.values()]
  } finally {
    essenceOptionsLoading.value = false
    essenceOptionsLoaded.value = true
  }
}

onMounted(loadEssenceLocationOptions)

const syncLocalTableData = (tableData: Record<string, any> | null) => {
  localTableData.value = Object.fromEntries(
    MAAEND_PLAN_TIME_KEYS.map(timeKey => [
      timeKey,
      maaEndPlanKeyToSanityConfig(tableData?.[timeKey]),
    ])
  ) as Partial<Record<PlanTimeKey, MaaEndSanityConfig>>
}

watch(
  () => props.tableData,
  tableData => {
    syncLocalTableData(tableData)
  },
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
  { title: t('plan.week.ALL'), dataIndex: 'ALL', key: 'ALL', width: 160, align: 'center' },
  { title: t('plan.week.Monday'), dataIndex: 'Monday', key: 'Monday', width: 160, align: 'center' },
  {
    title: t('plan.week.Tuesday'),
    dataIndex: 'Tuesday',
    key: 'Tuesday',
    width: 160,
    align: 'center',
  },
  {
    title: t('plan.week.Wednesday'),
    dataIndex: 'Wednesday',
    key: 'Wednesday',
    width: 160,
    align: 'center',
  },
  {
    title: t('plan.week.Thursday'),
    dataIndex: 'Thursday',
    key: 'Thursday',
    width: 160,
    align: 'center',
  },
  { title: t('plan.week.Friday'), dataIndex: 'Friday', key: 'Friday', width: 160, align: 'center' },
  {
    title: t('plan.week.Saturday'),
    dataIndex: 'Saturday',
    key: 'Saturday',
    width: 160,
    align: 'center',
  },
  { title: t('plan.week.Sunday'), dataIndex: 'Sunday', key: 'Sunday', width: 160, align: 'center' },
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

const asTimeKey = (value: string): PlanTimeKey => value as PlanTimeKey

const isColumnDisabled = (timeKey: PlanTimeKey) => {
  if (props.currentMode === 'ALL') return timeKey !== 'ALL'
  return timeKey === 'ALL'
}

const getDayConfig = (timeKey: PlanTimeKey): MaaEndSanityConfig =>
  normalizeMaaEndSanityConfig(localTableData.value?.[timeKey])

const getCurrentTaskOptions = (timeKey: PlanTimeKey) => {
  const dayConfig = getDayConfig(timeKey)
  if (dayConfig.SanityTaskType === 'Essence') {
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
  return PROTOCOL_SPACE_TASK_OPTIONS_MAP[dayConfig.SanityTaskType as ProtocolSpaceTab]
}

const isEssenceLocationLoading = (timeKey: PlanTimeKey) =>
  essenceOptionsLoading.value && getDayConfig(timeKey).SanityTaskType === 'Essence'

const isRewardGroupEnabledForTime = (timeKey: PlanTimeKey) => {
  const dayConfig = getDayConfig(timeKey)
  if (dayConfig.SanityTaskType === 'Essence') return false
  return isProtocolSpaceRewardEnabled(dayConfig)
}

const configRows = computed(() => [
  {
    rowKey: 'SanityTaskType',
    fieldName: t('plan.table.sanityTask'),
    ...Object.fromEntries(
      MAAEND_PLAN_TIME_KEYS.map(timeKey => [timeKey, getDayConfig(timeKey).SanityTaskType])
    ),
  },
  {
    rowKey: 'CurrentTask',
    fieldName: t('plan.table.currentTask'),
    ...Object.fromEntries(
      MAAEND_PLAN_TIME_KEYS.map(timeKey => [timeKey, getCurrentTaskValue(getDayConfig(timeKey))])
    ),
  },
  {
    rowKey: 'RewardsSetOption',
    fieldName: t('plan.table.rewardsSet'),
    ...Object.fromEntries(
      MAAEND_PLAN_TIME_KEYS.map(timeKey => [timeKey, getDayConfig(timeKey).RewardsSetOption])
    ),
  },
])

const simpleRows = computed(() => {
  const timeKeys =
    props.currentMode === 'ALL'
      ? (['ALL'] as PlanTimeKey[])
      : MAAEND_PLAN_TIME_KEYS.filter(timeKey => timeKey !== 'ALL')

  return timeKeys.map(timeKey => {
    const dayConfig = getDayConfig(timeKey)
    return {
      key: timeKey,
      timeLabel: MAAEND_PLAN_TIME_LABELS[timeKey],
      SanityTaskType: dayConfig.SanityTaskType,
      CurrentTask: getCurrentTaskValue(dayConfig),
      RewardsSetOption: dayConfig.RewardsSetOption,
    }
  })
})

const saveDayConfig = async (timeKey: PlanTimeKey, config: Partial<MaaEndSanityConfig>) => {
  const normalized = normalizeMaaEndSanityConfig(config)
  const previous = localTableData.value[timeKey]

  localTableData.value = {
    ...localTableData.value,
    [timeKey]: normalized,
  }

  const saved = await props.handlePlanChange(
    `${timeKey}.Key`,
    normalizeMaaEndPlanKey(normalized),
    false
  )
  if (!saved) {
    localTableData.value = {
      ...localTableData.value,
      [timeKey]: previous ?? normalizeMaaEndSanityConfig(),
    }
  }
}

const handleSanityTaskTypeChange = async (timeKey: PlanTimeKey, value: SanityTaskType) => {
  await saveDayConfig(timeKey, {
    ...getDayConfig(timeKey),
    SanityTaskType: value,
  })
}

const handleTaskChange = async (timeKey: PlanTimeKey, value: CurrentTaskValue) => {
  const currentConfig = getDayConfig(timeKey)
  if (currentConfig.SanityTaskType === 'Essence') {
    await saveDayConfig(timeKey, {
      ...currentConfig,
      AutoEssenceSpecifiedLocation: value as MaaEndSanityConfig['AutoEssenceSpecifiedLocation'],
    })
    return
  }

  await saveDayConfig(timeKey, {
    ...currentConfig,
    [PROTOCOL_SPACE_TASK_FIELD_MAP[currentConfig.SanityTaskType as ProtocolSpaceTab]]:
      value as MaaEndSanityConfig['OperatorProgression'],
  })
}

const handleRewardChange = async (timeKey: PlanTimeKey, value: RewardSetOption) => {
  await saveDayConfig(timeKey, {
    ...getDayConfig(timeKey),
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
