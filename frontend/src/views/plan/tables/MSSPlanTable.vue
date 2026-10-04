<template>
  <div>
    <div v-show="viewMode === 'config'" class="config-table-wrapper">
      <a-table
        :key="`mss-config-table-${currentMode}`"
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
              v-if="record.rowKey === 'TribulationStage'"
              :value="record[column.key]"
              size="small"
              class="config-control"
              :bordered="false"
              :list-height="STAGE_LIST_HEIGHT"
              :disabled="isColumnDisabled(asTimeKey(column.key))"
              @update:value="(value: string) => handleStageChange(asTimeKey(column.key), value)"
            >
              <a-select-option v-for="stage in TRIBULATION_STAGES" :key="stage" :value="stage">
                {{ shortStage(stage) }}
              </a-select-option>
            </a-select>

            <a-select
              v-else-if="record.rowKey === 'Difficulty'"
              :value="record[column.key]"
              size="small"
              class="config-control"
              :bordered="false"
              :options="
                difficultyOptions(keyOf(asTimeKey(column.key)).TribulationStage).map(level => ({
                  label: level,
                  value: level,
                }))
              "
              :disabled="
                isColumnDisabled(asTimeKey(column.key)) ||
                isOverriddenBySwitch('Difficulty', asTimeKey(column.key))
              "
              @update:value="
                (value: number) => handleFieldChange(asTimeKey(column.key), { Difficulty: value })
              "
            />

            <a-switch
              v-else-if="record.rowKey === 'SkipDifficulty' || record.rowKey === 'ConsumeAllEnergy'"
              :checked="record[column.key]"
              size="small"
              :disabled="isColumnDisabled(asTimeKey(column.key))"
              @change="
                (checked: boolean) =>
                  handleFieldChange(asTimeKey(column.key), { [record.rowKey]: checked })
              "
            />

            <a-input-number
              v-else
              :value="record[column.key]"
              size="small"
              class="config-control"
              :min="1"
              :max="99"
              :disabled="
                isColumnDisabled(asTimeKey(column.key)) ||
                isOverriddenBySwitch(record.rowKey as string, asTimeKey(column.key))
              "
              @change="
                (value: number | null) =>
                  handleFieldChange(asTimeKey(column.key), { [record.rowKey]: value ?? 1 })
              "
            />
          </template>
        </template>
      </a-table>
    </div>

    <div v-show="viewMode === 'simple'" class="simple-table-wrapper">
      <a-table
        :key="`mss-simple-table-${currentMode}`"
        :columns="simpleColumns"
        :data-source="simpleRows"
        :pagination="false"
        class="simple-table"
        size="middle"
        :bordered="true"
        :scroll="{ x: 'max-content' }"
      >
        <template #bodyCell="{ column, record }">
          <a-select
            v-if="column.key === 'TribulationStage'"
            :value="record.TribulationStage"
            size="small"
            class="config-control"
            :bordered="false"
            :list-height="STAGE_LIST_HEIGHT"
            :disabled="isColumnDisabled(record.timeKey)"
            @update:value="(value: string) => handleStageChange(record.timeKey, value)"
          >
            <a-select-option v-for="stage in TRIBULATION_STAGES" :key="stage" :value="stage">
              {{ shortStage(stage) }}
            </a-select-option>
          </a-select>

          <a-select
            v-else-if="column.key === 'Difficulty'"
            :value="record.Difficulty"
            size="small"
            class="config-control"
            :bordered="false"
            :options="
              difficultyOptions(record.TribulationStage).map(level => ({
                label: level,
                value: level,
              }))
            "
            :disabled="
              isColumnDisabled(record.timeKey) || isOverriddenBySwitch('Difficulty', record.timeKey)
            "
            @update:value="
              (value: number) => handleFieldChange(record.timeKey, { Difficulty: value })
            "
          />

          <a-switch
            v-else-if="column.key === 'SkipDifficulty' || column.key === 'ConsumeAllEnergy'"
            :checked="record[column.key]"
            size="small"
            :disabled="isColumnDisabled(record.timeKey)"
            @change="
              (checked: boolean) => handleFieldChange(record.timeKey, { [column.key]: checked })
            "
          />

          <a-input-number
            v-else-if="column.key === 'FightTimes'"
            :value="record.FightTimes"
            size="small"
            class="config-control"
            :min="1"
            :max="99"
            :disabled="
              isColumnDisabled(record.timeKey) || isOverriddenBySwitch('FightTimes', record.timeKey)
            "
            @change="
              (value: number | null) =>
                handleFieldChange(record.timeKey, { FightTimes: value ?? 1 })
            "
          />
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { TIME_KEYS, type TimeKey } from '@/composables/usePlanDataCoordinator'
import type { PlanChangeHandler } from '@/utils/planTypeRegistry'

/**
 * 悬赏试炼关卡。
 *
 * 取值与顺序都要和后端 `constants.MSS_TRIBULATION_STAGES`、外壳 interface 的
 * `悬赏试炼关卡` cases 一致：写进实例配置的是这个列表里的下标，错位就会刷错关卡。
 * 上游加关卡时三处一起补。
 */
const TRIBULATION_STAGES = [
  '基础试炼',
  '晋升试炼-怪诞舞者',
  '晋升试炼-终宵萤辉',
  '晋升试炼-热嘟噜噗男爵',
  '技巧试炼-节奏游戏卡带',
  '技巧试炼-射击游戏卡带',
  '技巧试炼-格斗游戏卡带',
  '纹章试炼-好市民点数',
  '纹章试炼-协会贡献证',
  '纹章试炼-恩赐消费券',
] as const

/** 一个日期槽位里存的一整套悬赏试炼配置，字段与后端 MSSPlanKey 一一对应 */
interface StellaPlanKey {
  TribulationStage: string
  SkipDifficulty: boolean
  Difficulty: number
  ConsumeAllEnergy: boolean
  FightTimes: number
}

const DEFAULT_KEY: StellaPlanKey = {
  TribulationStage: TRIBULATION_STAGES[0],
  SkipDifficulty: false,
  Difficulty: 1,
  ConsumeAllEnergy: false,
  FightTimes: 1,
}

/**
 * 下拉面板的最大高度。
 *
 * antd 默认只给 256px，十个试炼关卡放不下、要拖着看；关卡表就这么长，
 * 直接放开到能一次列完（十项 × 行高 + 内边距，留了点余量）。
 */
const STAGE_LIST_HEIGHT = 320

interface Props {
  tableData: Record<string, any> | null
  currentMode: 'ALL' | 'Weekly'
  viewMode: 'config' | 'simple'
  planId?: string
  handlePlanChange: PlanChangeHandler
}

const props = defineProps<Props>()
const { t } = useI18n()

const asTimeKey = (value: string): TimeKey => value as TimeKey

/** 当前模式只认一列：ALL 模式看「全局」，Weekly 模式看具体星期 */
const isColumnDisabled = (timeKey: TimeKey) => {
  if (props.currentMode === 'ALL') return timeKey !== 'ALL'
  return timeKey === 'ALL'
}

/**
 * 被同一槽位里的开关压住的项：开了「跳过难度选择」难度就不起作用，开了「消耗所有干劲」
 * 作战次数就不起作用，两格跟着置灰。
 *
 * **只是置灰，值照留**：把开关关回去时原来的难度 / 次数还在，不用重填。
 */
const isOverriddenBySwitch = (rowKey: string, timeKey: TimeKey): boolean => {
  const key = keyOf(timeKey)
  if (rowKey === 'Difficulty') return key.SkipDifficulty
  if (rowKey === 'FightTimes') return key.ConsumeAllEnergy
  return false
}

/**
 * 单元格里只显示关卡自己的名字，去掉「晋升试炼-」这类前缀。
 *
 * **只影响显示**：写进外壳实例配置、以及下拉的取值都仍是 interface 里的完整
 * case 名，去掉前缀会对不上。
 */
const shortStage = (stage: string): string => {
  const index = stage.indexOf('-')
  return index === -1 ? stage : stage.slice(index + 1)
}

/**
 * 每种试炼的难度上限（用户 2026-09-23 告知）：
 * 晋升试炼 9 级、技巧试炼 6 级、纹章试炼 3 级；基础试炼没有难度，只给 1。
 *
 * 难度下拉的可选项由**当前槽位选的关卡**决定，所以换关卡时要把越界的难度夹回去。
 */
const STAGE_DIFFICULTY_LIMIT: Record<string, number> = {
  基础试炼: 1,
  '晋升试炼-怪诞舞者': 9,
  '晋升试炼-终宵萤辉': 9,
  '晋升试炼-热嘟噜噗男爵': 9,
  '技巧试炼-节奏游戏卡带': 6,
  '技巧试炼-射击游戏卡带': 6,
  '技巧试炼-格斗游戏卡带': 6,
  '纹章试炼-好市民点数': 3,
  '纹章试炼-协会贡献证': 3,
  '纹章试炼-恩赐消费券': 3,
}

const DEFAULT_DIFFICULTY_LIMIT = 9

const difficultyLimitOf = (stage: string): number =>
  STAGE_DIFFICULTY_LIMIT[stage] ?? DEFAULT_DIFFICULTY_LIMIT

const difficultyOptions = (stage: string) =>
  Array.from({ length: difficultyLimitOf(stage) }, (_, index) => index + 1)

/** 读某个日期槽位的完整配置，缺字段用默认值补齐 */
const keyOf = (timeKey: TimeKey): StellaPlanKey => {
  const raw = props.tableData?.[timeKey]?.Key as Partial<StellaPlanKey> | undefined
  const stage = typeof raw?.TribulationStage === 'string' ? raw.TribulationStage : ''
  const effectiveStage = stage || DEFAULT_KEY.TribulationStage
  const number = (value: unknown, fallback: number, max: number) => {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed >= 1 && parsed <= max ? parsed : fallback
  }
  return {
    TribulationStage: effectiveStage,
    SkipDifficulty: raw?.SkipDifficulty === true,
    Difficulty: number(raw?.Difficulty, DEFAULT_KEY.Difficulty, difficultyLimitOf(effectiveStage)),
    ConsumeAllEnergy: raw?.ConsumeAllEnergy === true,
    FightTimes: number(raw?.FightTimes, DEFAULT_KEY.FightTimes, 99),
  }
}

const days = (pick: (timeKey: TimeKey) => unknown) =>
  Object.fromEntries(TIME_KEYS.map(timeKey => [timeKey, pick(timeKey)]))

const configColumns = computed(() => [
  {
    title: t('plan.table.field'),
    dataIndex: 'fieldName',
    key: 'fieldName',
    width: 120,
    fixed: 'left',
    align: 'center',
  },
  // 列宽压到 130：八列加配置项列一共 1160px，一屏能全放下（与 MAA 那张表同口径）
  ...TIME_KEYS.map(timeKey => ({
    title: t(`plan.week.${timeKey}`),
    dataIndex: timeKey,
    key: timeKey,
    width: 130,
    align: 'center' as const,
  })),
])

const configRows = computed(() => [
  {
    rowKey: 'TribulationStage',
    fieldName: t('plan.table.tribulationStage'),
    ...days(timeKey => keyOf(timeKey).TribulationStage),
  },
  {
    rowKey: 'SkipDifficulty',
    fieldName: t('plan.table.skipDifficulty'),
    ...days(timeKey => keyOf(timeKey).SkipDifficulty),
  },
  {
    rowKey: 'Difficulty',
    fieldName: t('plan.table.difficulty'),
    ...days(timeKey => keyOf(timeKey).Difficulty),
  },
  {
    rowKey: 'ConsumeAllEnergy',
    fieldName: t('plan.table.consumeAllEnergy'),
    ...days(timeKey => keyOf(timeKey).ConsumeAllEnergy),
  },
  {
    rowKey: 'FightTimes',
    fieldName: t('plan.table.fightTimes'),
    ...days(timeKey => keyOf(timeKey).FightTimes),
  },
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
    title: t('plan.table.tribulationStage'),
    dataIndex: 'TribulationStage',
    key: 'TribulationStage',
    width: 180,
    align: 'center',
  },
  {
    title: t('plan.table.skipDifficulty'),
    dataIndex: 'SkipDifficulty',
    key: 'SkipDifficulty',
    width: 130,
    align: 'center',
  },
  {
    title: t('plan.table.difficulty'),
    dataIndex: 'Difficulty',
    key: 'Difficulty',
    width: 110,
    align: 'center',
  },
  {
    title: t('plan.table.consumeAllEnergy'),
    dataIndex: 'ConsumeAllEnergy',
    key: 'ConsumeAllEnergy',
    width: 140,
    align: 'center',
  },
  {
    title: t('plan.table.fightTimes'),
    dataIndex: 'FightTimes',
    key: 'FightTimes',
    width: 110,
    align: 'center',
  },
])

const simpleRows = computed(() =>
  TIME_KEYS.map(timeKey => ({
    key: timeKey,
    timeKey,
    timeLabel: t(`plan.week.${timeKey}`),
    ...keyOf(timeKey),
  }))
)

/** 改一项：把该槽位的整套配置合并回去，没动的字段保持原值 */
const handleFieldChange = async (timeKey: TimeKey, patch: Partial<StellaPlanKey>) => {
  await props.handlePlanChange(`${timeKey}.Key`, { ...keyOf(timeKey), ...patch }, false)
}

/** 换关卡：难度上限跟着关卡变，越界的难度夹回新上限 */
const handleStageChange = async (timeKey: TimeKey, stage: string) => {
  const current = keyOf(timeKey)
  await handleFieldChange(timeKey, {
    TribulationStage: stage,
    Difficulty: Math.min(current.Difficulty, difficultyLimitOf(stage)),
  })
}
</script>

<style scoped>
.config-table-wrapper,
.simple-table-wrapper {
  width: 100%;
}

.config-control {
  width: 100%;
}
</style>
