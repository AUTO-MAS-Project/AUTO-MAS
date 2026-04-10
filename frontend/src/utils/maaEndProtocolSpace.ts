export type PlanTimeKey =
  | 'ALL'
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'
  | 'Sunday'

export type PlanWeekdayKey = Exclude<PlanTimeKey, 'ALL'>

export type ProtocolSpaceTab = 'OperatorProgression' | 'WeaponProgression' | 'CrisisDrills'
export type CurrentTaskField = ProtocolSpaceTab
export type RewardSetOption = 'RewardsSetA' | 'RewardsSetB'
export type CurrentTaskValue =
  | 'OperatorEXP'
  | 'Promotions'
  | 'T-Creds'
  | 'SkillUp'
  | 'WeaponEXP'
  | 'WeaponTune'
  | 'AdvancedProgression1'
  | 'AdvancedProgression2'
  | 'AdvancedProgression3'
  | 'AdvancedProgression4'
  | 'AdvancedProgression5'

export interface ProtocolSpaceTaskOption {
  label: string
  value: CurrentTaskValue
  rewards?: boolean
}

export interface ProtocolSpaceConfig {
  ProtocolSpaceTab: ProtocolSpaceTab
  OperatorProgression: CurrentTaskValue
  WeaponProgression: CurrentTaskValue
  CrisisDrills: CurrentTaskValue
  RewardsSetOption: RewardSetOption
}

export const MAAEND_PLAN_TIME_KEYS: PlanTimeKey[] = [
  'ALL',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

export const MAAEND_PLAN_WEEKDAY_KEYS: PlanWeekdayKey[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

export const MAAEND_PLAN_TIME_LABELS: Record<PlanTimeKey, string> = {
  ALL: '全局',
  Monday: '周一',
  Tuesday: '周二',
  Wednesday: '周三',
  Thursday: '周四',
  Friday: '周五',
  Saturday: '周六',
  Sunday: '周日',
}

export const PROTOCOL_SPACE_OPTIONS: Array<{ label: string; value: ProtocolSpaceTab }> = [
  { label: '干员养成', value: 'OperatorProgression' },
  { label: '武器养成', value: 'WeaponProgression' },
  { label: '危境预演', value: 'CrisisDrills' },
]

export const REWARD_OPTIONS: Array<{ label: string; value: RewardSetOption }> = [
  { label: '奖励组 A', value: 'RewardsSetA' },
  { label: '奖励组 B', value: 'RewardsSetB' },
]

export const PROTOCOL_SPACE_TASK_OPTIONS_MAP: Record<ProtocolSpaceTab, ProtocolSpaceTaskOption[]> =
  {
    OperatorProgression: [
      { label: '干员经验', value: 'OperatorEXP', rewards: true },
      { label: '干员进阶', value: 'Promotions', rewards: true },
      { label: '钱币收集', value: 'T-Creds' },
      { label: '技能提升', value: 'SkillUp', rewards: true },
    ],
    WeaponProgression: [
      { label: '武器经验', value: 'WeaponEXP' },
      { label: '武器进阶', value: 'WeaponTune', rewards: true },
    ],
    CrisisDrills: [
      { label: '高阶培养 I - D96钢样品四', value: 'AdvancedProgression1' },
      { label: '高阶培养 II - 超距辉映管', value: 'AdvancedProgression2' },
      { label: '高阶培养 III - 快子遴捡晶格', value: 'AdvancedProgression3' },
      { label: '高阶培养 IV - 象限拟合液', value: 'AdvancedProgression4' },
      { label: '高阶培养 V - 三相纳米片', value: 'AdvancedProgression5' },
    ],
  }

export const PROTOCOL_SPACE_TASK_FIELD_MAP: Record<ProtocolSpaceTab, CurrentTaskField> = {
  OperatorProgression: 'OperatorProgression',
  WeaponProgression: 'WeaponProgression',
  CrisisDrills: 'CrisisDrills',
}

export const PROTOCOL_SPACE_LABEL_MAP = Object.fromEntries(
  PROTOCOL_SPACE_OPTIONS.map(option => [option.value, option.label])
) as Record<ProtocolSpaceTab, string>

export const PROTOCOL_SPACE_TASK_LABEL_MAP = Object.fromEntries(
  Object.values(PROTOCOL_SPACE_TASK_OPTIONS_MAP)
    .flat()
    .map(option => [option.value, option.label])
) as Record<CurrentTaskValue, string>

export const PROTOCOL_SPACE_TASK_TITLE_MAP: Record<ProtocolSpaceTab, string> = {
  OperatorProgression: '干员养成任务',
  WeaponProgression: '武器养成任务',
  CrisisDrills: '危境预演任务',
}

export const PROTOCOL_SPACE_TASK_TOOLTIP_MAP: Record<ProtocolSpaceTab, string> = {
  OperatorProgression: '选择要执行的干员养成任务',
  WeaponProgression: '选择要执行的武器养成任务',
  CrisisDrills: '选择要执行的危境预演任务',
}

export const REWARD_LABEL_MAP = Object.fromEntries(
  REWARD_OPTIONS.map(option => [option.value, option.label])
) as Record<RewardSetOption, string>

export const createDefaultProtocolSpaceConfig = (): ProtocolSpaceConfig => ({
  ProtocolSpaceTab: 'OperatorProgression',
  OperatorProgression: 'OperatorEXP',
  WeaponProgression: 'WeaponEXP',
  CrisisDrills: 'AdvancedProgression1',
  RewardsSetOption: 'RewardsSetA',
})

export const getProtocolSpaceTaskField = (tab: ProtocolSpaceTab): CurrentTaskField =>
  PROTOCOL_SPACE_TASK_FIELD_MAP[tab]

export const getProtocolSpaceTaskOptions = (tab: ProtocolSpaceTab): ProtocolSpaceTaskOption[] =>
  PROTOCOL_SPACE_TASK_OPTIONS_MAP[tab]

export const getCurrentProtocolTaskValue = (config: ProtocolSpaceConfig): CurrentTaskValue =>
  config[getProtocolSpaceTaskField(config.ProtocolSpaceTab)]

export const isProtocolSpaceRewardEnabled = (config: ProtocolSpaceConfig): boolean => {
  const currentTask = getCurrentProtocolTaskValue(config)
  return getProtocolSpaceTaskOptions(config.ProtocolSpaceTab).some(
    option => option.value === currentTask && option.rewards
  )
}

export const normalizeProtocolSpaceConfig = (
  rawConfig?: Partial<ProtocolSpaceConfig> | null
): ProtocolSpaceConfig => {
  const config = {
    ...createDefaultProtocolSpaceConfig(),
    ...(rawConfig ?? {}),
  } as ProtocolSpaceConfig

  const currentField = getProtocolSpaceTaskField(config.ProtocolSpaceTab)
  const validTaskOptions = getProtocolSpaceTaskOptions(config.ProtocolSpaceTab)

  if (!validTaskOptions.some(option => option.value === config[currentField])) {
    config[currentField] = validTaskOptions[0].value
  }

  if (!isProtocolSpaceRewardEnabled(config)) {
    config.RewardsSetOption = 'RewardsSetA'
  }

  return config
}
