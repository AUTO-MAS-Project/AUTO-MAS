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
              v-if="record.key === 'ProtocolSpaceTab'"
              :value="record[column.key]"
              size="small"
              class="config-select"
              :bordered="false"
              :disabled="isColumnDisabled(asTimeKey(column.key))"
              @update:value="handleProtocolSpaceChange(asTimeKey(column.key), $event)"
            >
              <a-select-option
                v-for="option in PROTOCOL_SPACE_OPTIONS"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </a-select-option>
            </a-select>

            <a-select
              v-else-if="record.key === 'CurrentTask'"
              :value="record[column.key]"
              size="small"
              class="config-select"
              :bordered="false"
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

          <template v-else-if="column.key === 'ProtocolSpaceTab'">
            <a-select
              :value="record.ProtocolSpaceTab"
              size="small"
              class="config-select"
              :bordered="false"
              :disabled="isColumnDisabled(record.key)"
              @update:value="handleProtocolSpaceChange(record.key, $event)"
            >
              <a-select-option
                v-for="option in PROTOCOL_SPACE_OPTIONS"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </a-select-option>
            </a-select>
          </template>

          <template v-else-if="column.key === 'CurrentTask'">
            <a-select
              :value="record.CurrentTask"
              size="small"
              class="config-select"
              :bordered="false"
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
          </template>

          <template v-else>
            <a-select
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
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  MAAEND_PLAN_TIME_KEYS,
  MAAEND_PLAN_TIME_LABELS,
  PROTOCOL_SPACE_OPTIONS,
  PROTOCOL_SPACE_TASK_OPTIONS_MAP,
  REWARD_OPTIONS,
  getCurrentProtocolTaskValue,
  normalizeProtocolSpaceConfig,
  isProtocolSpaceRewardEnabled,
  type CurrentTaskValue,
  type PlanTimeKey,
  type ProtocolSpaceConfig,
  type ProtocolSpaceTab,
  type RewardSetOption,
} from '@/utils/maaEndProtocolSpace'

interface Props {
  tableData: Record<string, any> | null
  currentMode: 'ALL' | 'Weekly'
  viewMode: 'config' | 'simple'
  planId?: string
  // eslint-disable-next-line no-unused-vars
  handlePlanChange: (...args: [string, any]) => Promise<void>
}

const props = defineProps<Props>()

const configColumns = [
  {
    title: '配置项',
    dataIndex: 'fieldName',
    key: 'fieldName',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  { title: '全局', dataIndex: 'ALL', key: 'ALL', width: 160, align: 'center' },
  { title: '周一', dataIndex: 'Monday', key: 'Monday', width: 160, align: 'center' },
  { title: '周二', dataIndex: 'Tuesday', key: 'Tuesday', width: 160, align: 'center' },
  { title: '周三', dataIndex: 'Wednesday', key: 'Wednesday', width: 160, align: 'center' },
  { title: '周四', dataIndex: 'Thursday', key: 'Thursday', width: 160, align: 'center' },
  { title: '周五', dataIndex: 'Friday', key: 'Friday', width: 160, align: 'center' },
  { title: '周六', dataIndex: 'Saturday', key: 'Saturday', width: 160, align: 'center' },
  { title: '周日', dataIndex: 'Sunday', key: 'Sunday', width: 160, align: 'center' },
]

const simpleColumns = [
  {
    title: '时间',
    dataIndex: 'timeLabel',
    key: 'timeLabel',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  {
    title: '协议空间',
    dataIndex: 'ProtocolSpaceTab',
    key: 'ProtocolSpaceTab',
    width: 180,
    align: 'center',
  },
  { title: '当前任务', dataIndex: 'CurrentTask', key: 'CurrentTask', width: 220, align: 'center' },
  {
    title: '奖励组',
    dataIndex: 'RewardsSetOption',
    key: 'RewardsSetOption',
    width: 160,
    align: 'center',
  },
]

const asTimeKey = (value: string): PlanTimeKey => value as PlanTimeKey

const isColumnDisabled = (timeKey: PlanTimeKey) => {
  if (props.currentMode === 'ALL') return timeKey !== 'ALL'
  return timeKey === 'ALL'
}

const getDayConfig = (timeKey: PlanTimeKey): ProtocolSpaceConfig =>
  normalizeProtocolSpaceConfig(props.tableData?.[timeKey])

const getCurrentTaskOptions = (timeKey: PlanTimeKey) =>
  PROTOCOL_SPACE_TASK_OPTIONS_MAP[getDayConfig(timeKey).ProtocolSpaceTab]

const isRewardGroupEnabledForTime = (timeKey: PlanTimeKey) =>
  isProtocolSpaceRewardEnabled(getDayConfig(timeKey))

const configRows = computed(() => [
  {
    key: 'ProtocolSpaceTab',
    fieldName: '协议空间',
    ...Object.fromEntries(
      MAAEND_PLAN_TIME_KEYS.map(timeKey => [timeKey, getDayConfig(timeKey).ProtocolSpaceTab])
    ),
  },
  {
    key: 'CurrentTask',
    fieldName: '当前任务',
    ...Object.fromEntries(
      MAAEND_PLAN_TIME_KEYS.map(timeKey => [
        timeKey,
        getCurrentProtocolTaskValue(getDayConfig(timeKey)),
      ])
    ),
  },
  {
    key: 'RewardsSetOption',
    fieldName: '奖励组',
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
      ProtocolSpaceTab: dayConfig.ProtocolSpaceTab,
      CurrentTask: getCurrentProtocolTaskValue(dayConfig),
      RewardsSetOption: dayConfig.RewardsSetOption,
    }
  })
})

const saveDayConfig = async (timeKey: PlanTimeKey, config: Partial<ProtocolSpaceConfig>) => {
  await props.handlePlanChange(timeKey, normalizeProtocolSpaceConfig(config))
}

const handleProtocolSpaceChange = async (timeKey: PlanTimeKey, value: ProtocolSpaceTab) => {
  await saveDayConfig(timeKey, {
    ...getDayConfig(timeKey),
    ProtocolSpaceTab: value,
  })
}

const handleTaskChange = async (timeKey: PlanTimeKey, value: CurrentTaskValue) => {
  const currentConfig = getDayConfig(timeKey)
  await saveDayConfig(timeKey, {
    ...currentConfig,
    [currentConfig.ProtocolSpaceTab]: value,
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
