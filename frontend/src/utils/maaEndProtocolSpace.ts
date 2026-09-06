import type { ComboBoxItem } from '@/api'

// Frontend mirror of app/utils/constants.py. Keep fixed protocol-space values in sync
// with the backend; AutoEssence locations come from MaaEnd's dynamic resource API.
export const MAAEND_DELIVERY_COMMISSION_SOURCE_OPTIONS = [
  { label: '不限', value: 'Unlimited' },
  { label: '武陵城', value: 'WulingCity' },
  { label: '试验园区', value: 'TestArea' },
] as const

export type MaaEndDeliveryCommissionSource =
  (typeof MAAEND_DELIVERY_COMMISSION_SOURCE_OPTIONS)[number]['value']

export const MAAEND_AUTO_COLLECT_MODE_OPTIONS = [
  {
    labelKey: 'edit.maaEndAutoCollectModeDistributed',
    value: 'Distributed',
  },
  {
    labelKey: 'edit.maaEndAutoCollectModeConcentrated',
    value: 'Concentrated',
  },
] as const

export type MaaEndAutoCollectMode =
  (typeof MAAEND_AUTO_COLLECT_MODE_OPTIONS)[number]['value']

export const MAAEND_AUTO_COLLECT_ROUTE_OPTIONS = [
  { value: 'Route1', labelKey: 'edit.maaEndAutoCollectRoute1', regionKey: 'edit.maaEndRegionWulingCity' },
  { value: 'Route2', labelKey: 'edit.maaEndAutoCollectRoute2', regionKey: 'edit.maaEndRegionWulingCity' },
  { value: 'Route3', labelKey: 'edit.maaEndAutoCollectRoute3', regionKey: 'edit.maaEndRegionWulingCity' },
  { value: 'Route4', labelKey: 'edit.maaEndAutoCollectRoute4', regionKey: 'edit.maaEndRegionValleyNo4' },
  { value: 'Route5', labelKey: 'edit.maaEndAutoCollectRoute5', regionKey: 'edit.maaEndRegionValleyNo4' },
  { value: 'Route6', labelKey: 'edit.maaEndAutoCollectRoute6', regionKey: 'edit.maaEndRegionValleyNo4' },
  { value: 'Route7', labelKey: 'edit.maaEndAutoCollectRoute7', regionKey: 'edit.maaEndRegionWulingCity' },
  { value: 'Route8', labelKey: 'edit.maaEndAutoCollectRoute8', regionKey: 'edit.maaEndRegionWulingCity' },
  { value: 'Route9', labelKey: 'edit.maaEndAutoCollectRoute9', regionKey: 'edit.maaEndRegionWulingCity' },
  { value: 'Route10', labelKey: 'edit.maaEndAutoCollectRoute10', regionKey: 'edit.maaEndRegionWuling' },
  { value: 'Route11', labelKey: 'edit.maaEndAutoCollectRoute11', regionKey: 'edit.maaEndRegionWuling' },
  { value: 'Route12', labelKey: 'edit.maaEndAutoCollectRoute12', regionKey: 'edit.maaEndRegionWuling' },
  { value: 'Route13', labelKey: 'edit.maaEndAutoCollectRoute13', regionKey: 'edit.maaEndRegionValleyNo4' },
  { value: 'Route14', labelKey: 'edit.maaEndAutoCollectRoute14', regionKey: 'edit.maaEndRegionValleyNo4' },
  { value: 'Route15', labelKey: 'edit.maaEndAutoCollectRoute15', regionKey: 'edit.maaEndRegionWuling' },
] as const

export type MaaEndAutoCollectRoute =
  (typeof MAAEND_AUTO_COLLECT_ROUTE_OPTIONS)[number]['value']

export type MaaEndAutoCollectRegionKey =
  (typeof MAAEND_AUTO_COLLECT_ROUTE_OPTIONS)[number]['regionKey']

// 区域按选项中首次出现的顺序排列，组件按此顺序渲染分组面板
export const MAAEND_AUTO_COLLECT_ROUTE_REGIONS: MaaEndAutoCollectRegionKey[] = [
  ...new Set(MAAEND_AUTO_COLLECT_ROUTE_OPTIONS.map(option => option.regionKey)),
]

export const MAAEND_AUTO_COLLECT_COMMON_ROUTE_OPTIONS = [
  { value: 'CommonRoute1', labelKey: 'edit.maaEndAutoCollectCommonRoute1' },
  { value: 'CommonRoute2', labelKey: 'edit.maaEndAutoCollectCommonRoute2' },
  { value: 'CommonRoute3', labelKey: 'edit.maaEndAutoCollectCommonRoute3' },
  { value: 'CommonRoute4', labelKey: 'edit.maaEndAutoCollectCommonRoute4' },
  { value: 'CommonRoute5', labelKey: 'edit.maaEndAutoCollectCommonRoute5' },
  { value: 'CommonRoute6', labelKey: 'edit.maaEndAutoCollectCommonRoute6' },
  { value: 'CommonRoute7', labelKey: 'edit.maaEndAutoCollectCommonRoute7' },
  { value: 'CommonRoute8', labelKey: 'edit.maaEndAutoCollectCommonRoute8' },
] as const

export type MaaEndAutoCollectCommonRoute =
  (typeof MAAEND_AUTO_COLLECT_COMMON_ROUTE_OPTIONS)[number]['value']

export const PROTOCOL_SPACE_OPTIONS = [
  { label: '干员养成', value: 'OperatorProgression' },
  { label: '武器养成', value: 'WeaponProgression' },
  { label: '危境预演', value: 'CrisisDrills' },
] as const

export type ProtocolSpaceTab = (typeof PROTOCOL_SPACE_OPTIONS)[number]['value']
export type CurrentTaskField = ProtocolSpaceTab

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

export const MAAEND_PLAN_WEEKDAY_KEYS: PlanWeekdayKey[] = MAAEND_PLAN_TIME_KEYS.filter(
  (key): key is PlanWeekdayKey => key !== 'ALL'
)

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

export const SANITY_TASK_TYPE_OPTIONS = [
  ...PROTOCOL_SPACE_OPTIONS,
  { label: '基质刷取', value: 'Essence' },
] as const

export type SanityTaskType = (typeof SANITY_TASK_TYPE_OPTIONS)[number]['value']

export const REWARD_OPTIONS = [
  { label: '奖励组 A', value: 'RewardsSetA' },
  { label: '奖励组 B', value: 'RewardsSetB' },
] as const

export type RewardSetOption = (typeof REWARD_OPTIONS)[number]['value']

export type AutoEssenceLocation = string

export const PROTOCOL_SPACE_TASK_OPTIONS_MAP = {
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
} as const

export type ProtocolSpaceTaskValue =
  (typeof PROTOCOL_SPACE_TASK_OPTIONS_MAP)[ProtocolSpaceTab][number]['value']
export type CurrentTaskValue = ProtocolSpaceTaskValue | AutoEssenceLocation

export const MAAEND_TASK_GROUPS = [
  {
    key: 'Sanity',
    label: '🧠 理智作战',
    tasks: [
      { name: 'Sanity', label: '🧠 理智任务' },
      { name: 'AutoUseSpMedication', label: '💊 应急理智加强剂' },
    ],
  },
  {
    key: 'Infrastructure',
    label: '🏗️ 基建任务',
    tasks: [
      { name: 'DijiangRewards', label: '🎁 基建任务' },
      { name: 'DeliveryJobs', label: '🚚 转交委托' },
      { name: 'SellProduct', label: '🛒 售卖产品' },
      { name: 'AutoStockpile', label: '📦 自动囤货' },
      { name: 'AutoStockStaple', label: '🏪 购买稳定物资' },
    ],
  },
  {
    key: 'Credit',
    label: '💳 信用收支',
    tasks: [
      { name: 'VisitFriends', label: '🤝 拜访好友' },
      { name: 'CreditShoppingN2', label: '🛍️ 信用点购物' },
    ],
  },
  {
    key: 'Frontend',
    label: '🌾 前台任务',
    tasks: [
      { name: 'AutoEcoFarm', label: '🌾 生态农场' },
      { name: 'AutoSell', label: '💰 售卖弹性物资' },
      { name: 'EnvironmentMonitoring', label: '🌿 环境监测' },
      { name: 'TrialOfSwordmancy', label: '🗡️ 选剑演武' },
    ],
  },
  {
    key: 'Rewards',
    label: '🎖️ 奖励领取',
    tasks: [
      { name: 'DailyRewards', label: '📅 日常奖励领取' },
      { name: 'ResourceRecycleStation', label: '🦉 资源回收站' },
    ],
  },
  {
    key: 'Statistics',
    label: '📊 数据统计',
    tasks: [{ name: 'PullCountCalculator', label: '🧮 抽数计算' }],
  },
] as const

export type MaaEndTaskSwitch = (typeof MAAEND_TASK_GROUPS)[number]['tasks'][number]['name']

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

export interface MaaEndProtocolSpacePlanKey {
  SanityTaskType: ProtocolSpaceTab
  OperatorProgression: MaaEndSanityConfig['OperatorProgression']
  WeaponProgression: MaaEndSanityConfig['WeaponProgression']
  CrisisDrills: MaaEndSanityConfig['CrisisDrills']
  RewardsSetOption: RewardSetOption
}

export interface MaaEndAutoEssencePlanKey {
  SanityTaskType: 'Essence'
  AutoEssenceSpecifiedLocation: AutoEssenceLocation
}

export type MaaEndPlanKey = MaaEndProtocolSpacePlanKey | MaaEndAutoEssencePlanKey

type MaaEndLegacyPlanKey = Omit<Partial<MaaEndSanityConfig>, 'SanityTaskType'> & {
  SanityTaskType?: SanityTaskType | 'ProtocolSpace' | 'Matrix' | 'AutoEssence'
  ProtocolSpaceTab?: ProtocolSpaceTab
}

export interface MaaEndTaskSwitchItem {
  name: MaaEndTaskSwitch
  label: string
}

export interface MaaEndTaskSwitchGroup {
  key: string
  label: string
  tasks: MaaEndTaskSwitchItem[]
}

export type ProtocolSpaceConfig = MaaEndSanityConfig

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
  AutoEssenceSpecifiedLocation: '',
})

export const getProtocolSpaceTaskField = (tab: ProtocolSpaceTab): CurrentTaskField =>
  PROTOCOL_SPACE_TASK_FIELD_MAP[tab]

export const getProtocolSpaceTaskOptions = (
  tab: ProtocolSpaceTab
): readonly ProtocolSpaceTaskOption[] => PROTOCOL_SPACE_TASK_OPTIONS_MAP[tab]

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

export const getSanityTaskDisplayValue = (
  rawConfig?: Partial<MaaEndSanityConfig> | null,
  essenceLocationOptions: readonly ComboBoxItem[] = []
) => {
  const config = normalizeMaaEndSanityConfig(rawConfig)
  if (config.SanityTaskType === 'Essence') {
    return (
      essenceLocationOptions.find(option => option.value === config.AutoEssenceSpecifiedLocation)
        ?.label || config.AutoEssenceSpecifiedLocation
    )
  }
  return PROTOCOL_SPACE_TASK_LABEL_MAP[getCurrentProtocolTaskValue(config)]
}

export const normalizeMaaEndSanityConfig = (
  rawConfig?: MaaEndLegacyPlanKey | null
): MaaEndSanityConfig => {
  const config = {
    ...createDefaultMaaEndSanityConfig(),
    ...(rawConfig ?? {}),
  } as MaaEndSanityConfig

  if (!SANITY_TASK_TYPE_LABEL_MAP[config.SanityTaskType]) {
    config.SanityTaskType = 'OperatorProgression'
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

export const maaEndPlanKeyToSanityConfig = (rawSlot?: unknown): MaaEndSanityConfig => {
  const slot = rawSlot && typeof rawSlot === 'object' ? (rawSlot as Record<string, unknown>) : {}
  const rawKey = slot.Key && typeof slot.Key === 'object' ? slot.Key : slot
  const legacyKey = { ...(rawKey as MaaEndLegacyPlanKey) }

  if (legacyKey.SanityTaskType === 'ProtocolSpace') {
    const protocolSpaceTab = legacyKey.ProtocolSpaceTab
    if (PROTOCOL_SPACE_OPTIONS.some(option => option.value === protocolSpaceTab)) {
      legacyKey.SanityTaskType = protocolSpaceTab as ProtocolSpaceTab
    }
  } else if (legacyKey.SanityTaskType === 'Matrix' || legacyKey.SanityTaskType === 'AutoEssence') {
    legacyKey.SanityTaskType = 'Essence'
  }

  return normalizeMaaEndSanityConfig(legacyKey)
}

export const normalizeMaaEndPlanKey = (rawSlot?: unknown): MaaEndPlanKey => {
  const config = maaEndPlanKeyToSanityConfig(rawSlot)
  if (config.SanityTaskType === 'Essence') {
    return {
      SanityTaskType: 'Essence',
      AutoEssenceSpecifiedLocation: config.AutoEssenceSpecifiedLocation,
    }
  }

  return {
    SanityTaskType: config.SanityTaskType,
    OperatorProgression: config.OperatorProgression,
    WeaponProgression: config.WeaponProgression,
    CrisisDrills: config.CrisisDrills,
    RewardsSetOption: config.RewardsSetOption,
  }
}

// 保留旧导出，兼容既有调用
export const createDefaultProtocolSpaceConfig = (): ProtocolSpaceConfig =>
  createDefaultMaaEndSanityConfig()

export const normalizeProtocolSpaceConfig = (
  rawConfig?: Partial<ProtocolSpaceConfig> | null
): ProtocolSpaceConfig => normalizeMaaEndSanityConfig(rawConfig)
