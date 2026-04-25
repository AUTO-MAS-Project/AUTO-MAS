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

export type SanityTaskType =
  | 'OperatorProgression'
  | 'WeaponProgression'
  | 'CrisisDrills'
  | 'Essence'
export type ProtocolSpaceTab = Exclude<SanityTaskType, 'Essence'>
export type CurrentTaskField = ProtocolSpaceTab
export type RewardSetOption = 'RewardsSetA' | 'RewardsSetB'
export type ProtocolSpaceTaskValue =
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
export type AutoEssenceLocation =
  | 'VFTheHub'
  | 'VFOriginiumSciencePark'
  | 'VFOriginLodespring'
  | 'VFPowerPlateau'
  | 'WLWulingCity'
  | 'WLQingboStockade'
export type CurrentTaskValue = ProtocolSpaceTaskValue | AutoEssenceLocation

export interface ProtocolSpaceTaskOption {
  label: string
  value: ProtocolSpaceTaskValue
  rewards?: boolean
}

export interface MaaEndSanityConfig {
  SanityTaskType: SanityTaskType
  OperatorProgression: ProtocolSpaceTaskValue
  WeaponProgression: ProtocolSpaceTaskValue
  CrisisDrills: ProtocolSpaceTaskValue
  RewardsSetOption: RewardSetOption
  AutoEssenceSpecifiedLocation: AutoEssenceLocation
}

// 保留旧别名，避免历史引用爆炸
export type ProtocolSpaceConfig = MaaEndSanityConfig

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

export const SANITY_TASK_TYPE_OPTIONS: Array<{ label: string; value: SanityTaskType }> = [
  { label: '干员养成', value: 'OperatorProgression' },
  { label: '武器养成', value: 'WeaponProgression' },
  { label: '危境预演', value: 'CrisisDrills' },
  { label: '基质刷取', value: 'Essence' },
]

export const PROTOCOL_SPACE_OPTIONS: Array<{ label: string; value: ProtocolSpaceTab }> = [
  { label: '干员养成', value: 'OperatorProgression' },
  { label: '武器养成', value: 'WeaponProgression' },
  { label: '危境预演', value: 'CrisisDrills' },
]

export const REWARD_OPTIONS: Array<{ label: string; value: RewardSetOption }> = [
  { label: '奖励组 A', value: 'RewardsSetA' },
  { label: '奖励组 B', value: 'RewardsSetB' },
]

export const AUTO_ESSENCE_LOCATION_OPTIONS: Array<{
  label: string
  value: AutoEssenceLocation
}> = [
  { label: '枢纽区', value: 'VFTheHub' },
  { label: '源石研究园', value: 'VFOriginiumSciencePark' },
  { label: '矿脉源区', value: 'VFOriginLodespring' },
  { label: '供能高地', value: 'VFPowerPlateau' },
  { label: '武陵城区', value: 'WLWulingCity' },
  { label: '清波寨', value: 'WLQingboStockade' },
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

export const SANITY_TASK_TYPE_LABEL_MAP = Object.fromEntries(
  SANITY_TASK_TYPE_OPTIONS.map(option => [option.value, option.label])
) as Record<SanityTaskType, string>

export const PROTOCOL_SPACE_LABEL_MAP = Object.fromEntries(
  PROTOCOL_SPACE_OPTIONS.map(option => [option.value, option.label])
) as Record<ProtocolSpaceTab, string>

export const PROTOCOL_SPACE_TASK_LABEL_MAP = Object.fromEntries(
  Object.values(PROTOCOL_SPACE_TASK_OPTIONS_MAP)
    .flat()
    .map(option => [option.value, option.label])
) as Record<ProtocolSpaceTaskValue, string>

export const AUTO_ESSENCE_LOCATION_LABEL_MAP = Object.fromEntries(
  AUTO_ESSENCE_LOCATION_OPTIONS.map(option => [option.value, option.label])
) as Record<AutoEssenceLocation, string>

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

export const createDefaultMaaEndSanityConfig = (): MaaEndSanityConfig => ({
  SanityTaskType: 'OperatorProgression',
  OperatorProgression: 'OperatorEXP',
  WeaponProgression: 'WeaponEXP',
  CrisisDrills: 'AdvancedProgression1',
  RewardsSetOption: 'RewardsSetA',
  AutoEssenceSpecifiedLocation: 'VFTheHub',
})

export const getProtocolSpaceTaskField = (tab: ProtocolSpaceTab): CurrentTaskField =>
  PROTOCOL_SPACE_TASK_FIELD_MAP[tab]

export const getProtocolSpaceTaskOptions = (tab: ProtocolSpaceTab): ProtocolSpaceTaskOption[] =>
  PROTOCOL_SPACE_TASK_OPTIONS_MAP[tab]

export const getCurrentProtocolTaskValue = (config: MaaEndSanityConfig): ProtocolSpaceTaskValue =>
  config[getProtocolSpaceTaskField(config.SanityTaskType as ProtocolSpaceTab)]

export const getCurrentTaskValue = (config: MaaEndSanityConfig): CurrentTaskValue => {
  if (config.SanityTaskType === 'Essence') {
    return config.AutoEssenceSpecifiedLocation
  }
  return getCurrentProtocolTaskValue(config)
}

export const isProtocolSpaceRewardEnabled = (config: MaaEndSanityConfig): boolean => {
  const currentTask = getCurrentProtocolTaskValue(config)
  return getProtocolSpaceTaskOptions(config.SanityTaskType as ProtocolSpaceTab).some(
    option => option.value === currentTask && option.rewards
  )
}

export const getSanityTaskDisplayValue = (rawConfig?: Partial<MaaEndSanityConfig> | null) => {
  const config = normalizeMaaEndSanityConfig(rawConfig)
  if (config.SanityTaskType === 'Essence') {
    return AUTO_ESSENCE_LOCATION_LABEL_MAP[config.AutoEssenceSpecifiedLocation]
  }
  return PROTOCOL_SPACE_TASK_LABEL_MAP[getCurrentProtocolTaskValue(config)]
}

export const normalizeMaaEndSanityConfig = (
  rawConfig?: Partial<MaaEndSanityConfig> | null
): MaaEndSanityConfig => {
  const config = {
    ...createDefaultMaaEndSanityConfig(),
    ...(rawConfig ?? {}),
  } as MaaEndSanityConfig

  if (!SANITY_TASK_TYPE_LABEL_MAP[config.SanityTaskType]) {
    config.SanityTaskType = 'OperatorProgression'
  }
  if (!AUTO_ESSENCE_LOCATION_LABEL_MAP[config.AutoEssenceSpecifiedLocation]) {
    config.AutoEssenceSpecifiedLocation = 'VFTheHub'
  }
  if (!REWARD_LABEL_MAP[config.RewardsSetOption]) {
    config.RewardsSetOption = 'RewardsSetA'
  }

  if (config.SanityTaskType !== 'Essence') {
    const currentField = getProtocolSpaceTaskField(config.SanityTaskType)
    const validTaskOptions = getProtocolSpaceTaskOptions(config.SanityTaskType)
    if (!validTaskOptions.some(option => option.value === config[currentField])) {
      config[currentField] = validTaskOptions[0].value
    }
  }

  if (config.SanityTaskType === 'Essence') {
    config.RewardsSetOption = 'RewardsSetA'
  } else if (!isProtocolSpaceRewardEnabled(config)) {
    config.RewardsSetOption = 'RewardsSetA'
  }

  return config
}

// 保留旧导出，兼容既有调用
export const createDefaultProtocolSpaceConfig = (): ProtocolSpaceConfig =>
  createDefaultMaaEndSanityConfig()

export const normalizeProtocolSpaceConfig = (
  rawConfig?: Partial<ProtocolSpaceConfig> | null
): ProtocolSpaceConfig => normalizeMaaEndSanityConfig(rawConfig)
