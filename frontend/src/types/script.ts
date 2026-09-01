// 脚本类型定义
import type {
  HSRConfig,
  HSRConfig_TaskMapping,
  MaaConfig,
  GeneralConfig,
  OkwwConfig,
  OkNteConfig,
  SrcConfig,
  MaaEndConfig,
  M9AConfig,
  BetterGIConfig,
} from '@/api'
import type {
  AutoEssenceLocation,
  MaaEndTaskSwitch,
  ProtocolSpaceTaskValue,
  RewardSetOption,
  SanityTaskType,
} from '@/utils/maaEndProtocolSpace'

export type ScriptType =
  | 'MAA'
  | 'General'
  | 'Okww'
  | 'OkNte'
  | 'SRC'
  | 'MaaEnd'
  | 'M9A'
  | 'MaaFW'
  | 'HSR'
  | 'BetterGI'

export type OkwwScriptConfig = OkwwConfig
export type OkNteScriptConfig = OkNteConfig
export type BetterGIScriptConfig = BetterGIConfig
// MAA脚本配置
export interface MAAScriptConfig {
  Info: {
    Name: string
    Path: string
  }
  Run: {
    TaskTransitionMethod: string
    ProxyTimesLimit: number
    ADBSearchRange: number
    RunTimesLimit: number
    AnnihilationTimeLimit: number
    RoutineTimeLimit: number
    IfCheckGameUpdate: boolean
    IfAutoInstallGameApk: boolean
    GameUpdateTimeLimit: number
  }
  Emulator: {
    Id: string
    Index: string
  }
  SubConfigsInfo: {
    UserData: {
      instances: unknown[]
    }
  }
}

// 通用脚本配置
export interface GeneralScriptConfig {
  Game: {
    Arguments: string
    Enabled: boolean
    IfForceClose: boolean
    Path: string
    Type: string
    WaitTime: number
    EmulatorId: string
    EmulatorIndex: string
    URL: string
    ProcessName: string
  }
  Info: {
    Name: string
    RootPath: string
  }
  Run: {
    ProxyTimesLimit: number
    RunTimeLimit: number
    RunTimesLimit: number
  }
  Script: {
    Arguments: string
    ConfigPath: string
    ConfigPathMode: string
    ErrorLog: string
    IfTrackProcess: boolean
    TrackProcessName: string
    TrackProcessExe: string
    TrackProcessCmdline: string
    LogPath: string
    LogPathFormat: string
    LogTimeEnd: number
    LogTimeStart: number
    LogTimeFormat: string
    LogHookEnabled: boolean
    LogHookRules: string
    PushLogEnabled: boolean
    PushLogPatterns: string
    ScriptPath: string
    SuccessLog: string
    SuccessLogMode: string
    ErrorLogMode: string
    UpdateConfigMode: string
  }
  SubConfigsInfo: {
    UserData: {
      instances: unknown[]
    }
  }
}

// SRC脚本配置
export interface SRCScriptConfig {
  Info: {
    Name: string
    Path: string
  }
  Run: {
    TaskTransitionMethod: string
    ProxyTimesLimit: number
    RunTimesLimit: number
    RunTimeLimit: number
  }
  Emulator: {
    Id: string
    Index: string
  }
}

export type MaaEndTaskSwitchConfig = Record<`If${MaaEndTaskSwitch}`, boolean>

export type MaaEndTaskConfig = MaaEndTaskSwitchConfig & {
  SanityTaskType: SanityTaskType
  OperatorProgression: ProtocolSpaceTaskValue
  WeaponProgression: ProtocolSpaceTaskValue
  CrisisDrills: ProtocolSpaceTaskValue
  RewardsSetOption: RewardSetOption
  AutoEssenceSpecifiedLocation: AutoEssenceLocation
}

// MaaEnd脚本配置
export interface MaaEndScriptConfig {
  Info: {
    Name: string
    Path: string
  }
  Run: {
    RunTimeLimit: number
    ProxyTimesLimit: number
    RunTimesLimit: number
    AccountSwitchMethod: 'MAS' | 'MAAEND'
  }
  Game: {
    ControllerType: string | null
    Path: string
    Arguments: string
    WaitTime: number
    EmulatorId: string
    EmulatorIndex: string
    CloseOnFinish: boolean
  }
}

// M9A脚本配置
export interface M9AScriptConfig {
  Info: {
    Name: string
    Path: string
  }
  Emulator: {
    Id: string
    Index: string
  }
  Run: {
    ProxyTimesLimit: number
    RunTimesLimit: number
    RunTimeLimit: number
    IfAutoUpdateAfterQueue: boolean
    IfPsychubeDailyOnce: boolean
    IfSleepDreamMonthlyOnce: boolean
  }
  SubConfigsInfo: {
    UserData: {
      instances: unknown[]
    }
  }
}

// HSR 脚本配置（后端已通过 HSRConfig OpenAPI 暴露类型）
export type HSRScriptConfig = HSRConfig

// MaaFramework 项目脚本配置（宿主 Config v1；托管字段仍保留兼容读取）
export type MaaFWLaunchMode = 'AttachOnly' | 'DirectExe'

export interface MaaFWScriptConfig {
  Info: {
    Name: string
    ProjectLabel?: string
    Path: string
    Controller: string
    Resource: string
  }
  Emulator: {
    Id: string
    Index: string
  }
  Device: {
    AdbPath: string
    AdbAddress: string
    AdbScreencapMethods: number
    AdbInputMethods: number
    HWnd: number
    Win32ScreencapMethod: number
    Win32MouseMethod: number
    Win32KeyboardMethod: number
    GamepadType: number
    PlayCoverAddress: string
    PlayCoverUuid: string
  }
  Game: {
    LaunchMode: MaaFWLaunchMode
    LaunchPath: string
    Arguments: string
    WaitTime: number
    CloseOnFinish: boolean
  }
  Update: {
    IfAutoUpdate: boolean
    Source: '' | 'MirrorChyan' | 'GitHub'
    Channel: '' | 'stable' | 'beta'
    MirrorChyanCDK: string
    GitHubRepo: string
    GitHubTag: string
    GitHubAssetPattern: string
  }
  Managed: {
    Enabled: boolean
    ProjectId: string
    StoreId: string
    Version: string
    RuntimeConstraint: string
    ProjectManifest: string
    CheckoutPath: string
    PendingUpgrade: string
    LastOperation: string
  }
  ManagedRuntime: {
    RuntimeId: string
    PoolId: string
    PythonExecutable: string
    VenvPath: string
    RuntimeBinding: string
  }
  ManagedRemote: {
    Source: 'MirrorChyan' | 'GitHub'
    Channel: 'stable' | 'beta'
    MirrorChyanRID: string
    MirrorChyanCDK: string
    GitHubRepo: string
    GitHubTag: string
    GitHubAssetPattern: string
  }
  Run: {
    ProxyTimesLimit: number
    RunTimesLimit: number
    RunTimeLimit: number
    DailyOnceTasks: string | string[]
    WeeklyOnceTasks: string | string[]
    MonthlyOnceTasks: string | string[]
  }
  /**
   * 阶段性保留：manager.py 仍从 Selection.* 读取运行范围。
   * 回收版前端写入 Info.* / 用户任务配置，此字段仅用于兼容旧简版脚本编辑页读取。
   */
  Selection?: {
    Controller?: string | string[] | null
    Resource?: string | string[] | null
    Tasks?: string | string[] | null
  }
}

export type MaaFWTaskOptionValue = string | string[] | Record<string, string>

export interface MaaFWTaskSnapshot {
  taskOrder: string[]
  taskChecked: Record<string, boolean>
  taskOptions: Record<string, Record<string, MaaFWTaskOptionValue>>
}

export interface MaaFWUserConfig {
  Info: {
    Name: string
    Status: boolean
    RemainedDay: number
    IfScriptBeforeTask: boolean
    ScriptBeforeTask: string
    IfScriptAfterTask: boolean
    ScriptAfterTask: string
    Notes: string
    Tag?: string | null
    Account: string
    Password: string
    Resource?: string
  }
  Task: {
    SelectedPreset: string
    TaskSnapshot: string | MaaFWTaskSnapshot
  }
  Notify: {
    Enabled: boolean
    IfSendStatistic: boolean
    IfSendMail: boolean
    ToAddress: string
    IfServerChan: boolean
    ServerChanKey: string
  }
  Data: {
    LastProxyDate: string
    ProxyTimes: number
    IfPassCheck: boolean
    LastProxyStatus: string
    PeriodTaskRecords: string | Record<string, Record<string, string>>
  }
}

export interface MaaFWProjectInfo {
  name: string
  label?: string | null
  title?: string | null
  version?: string | null
  github?: string | null
  mirrorchyanRid?: string | null
  mirrorchyanMultiplatform?: boolean | null
  description?: string | null
  icon?: string | null
}

export const MAAFW_SUPPORTED_CONTROLLER_TYPES = ['Adb', 'Win32', 'Gamepad', 'PlayCover'] as const

export const isSupportedMaaFWControllerType = (type: string) =>
  (MAAFW_SUPPORTED_CONTROLLER_TYPES as readonly string[]).includes(type)

export interface MaaFWControllerInfo {
  name: string
  label?: string | null
  type: string
  description?: string | null
  icon?: string | null
  option: string[]
  permissionRequired: boolean
}

export interface MaaFWResourceInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  path: string[]
  controller: string[]
  option: string[]
}

export interface MaaFWGroupInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  defaultExpand: boolean
}

export interface MaaFWSettingInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  option: string[]
  defaultExpand: boolean
}

export interface MaaFWTaskInfo {
  name: string
  label?: string | null
  entry: string
  description?: string | null
  icon?: string | null
  group: string[]
  controller: string[]
  resource: string[]
  option: string[]
  defaultCheck: boolean
}

export interface MaaFWOptionCaseInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  option: string[]
}

export interface MaaFWOptionInputInfo {
  name: string
  label?: string | null
  description?: string | null
  icon?: string | null
  default?: string | null
  pipelineType?: string | null
  verify?: string | null
  verifyError?: string | null
  patternMsg?: string | null
}

export interface MaaFWOptionInfo {
  name: string
  type: string
  label?: string | null
  description?: string | null
  icon?: string | null
  controller: string[]
  resource: string[]
  cases: MaaFWOptionCaseInfo[]
  inputs: MaaFWOptionInputInfo[]
  hotkeys: Array<{
    name: string
    label?: string | null
    description?: string | null
    default?: string | null
  }>
  defaultCase?: string | string[] | null
}

export interface MaaFWAdbEmulatorExtraCapabilityInfo {
  screencap: boolean
  input: boolean
}

export interface MaaFWControlCapabilitiesInfo {
  emulatorExtras: Record<string, MaaFWAdbEmulatorExtraCapabilityInfo>
}

export interface MaaFWPresetInfo {
  name: string
  label?: string | null
  description?: string | null
  taskCount: number
  checkedCount: number
  snapshot: MaaFWTaskSnapshot
  controller?: string[]
  resource?: string[]
}

export interface MaaFWInterfacePreviewData {
  path: string
  project: MaaFWProjectInfo
  globalOption: string[]
  controlCapabilities: MaaFWControlCapabilitiesInfo
  controllers: MaaFWControllerInfo[]
  resources: MaaFWResourceInfo[]
  groups: MaaFWGroupInfo[]
  settings: MaaFWSettingInfo[]
  tasks: MaaFWTaskInfo[]
  options: MaaFWOptionInfo[]
  presets: MaaFWPresetInfo[]
  importCount: number
  agentCount: number
}

// HSR TaskMapping 默认值（Daily / ReceiveRewards / DivergentUniverse / CurrencyWars 默认走 SRA）
export const DEFAULT_HSR_TASK_MAPPING: HSRConfig_TaskMapping = {
  Daily: 'SRA',
  ReceiveRewards: 'SRA',
  DivergentUniverse: 'SRA',
  CurrencyWars: 'SRA',
}

/**
 * 解析 HSR 单个模块的执行脚本。
 * current 可用且在 available 中时优先保留，否则回退到仍可用的脚本。
 */
export function resolveTaskMappingValue(
  current: string | undefined,
  available: Set<'M7A' | 'SRA'>
): 'M7A' | 'SRA' | undefined {
  if (current && available.has(current as 'M7A' | 'SRA')) {
    return current as 'M7A' | 'SRA'
  }
  if (available.has('M7A')) return 'M7A'
  if (available.has('SRA')) return 'SRA'
  return undefined
}

// 脚本基础信息
export interface Script {
  id: string
  type: ScriptType
  name: string
  config:
    | MaaConfig
    | GeneralConfig
    | OkwwConfig
    | OkNteConfig
    | SrcConfig
    | MaaEndConfig
    | M9AConfig
    | MaaFWScriptConfig
    | HSRConfig
    | BetterGIConfig
  users: User[]
}

// 用户配置
export interface User {
  id: string
  name: string
  Data: {
    LastProxyDate: string
    LastPsychubeDate?: string
    LastLimboMonth?: string
    LastLucidscapeMonth?: string
    ProxyTimes: number
  }
  Info: {
    Annihilation: string
    Id: string
    InfrastMode: string
    InfrastName: string
    InfrastIndex: string
    MedicineNumb: number
    Mode: string
    Name: string
    SanityMode?: string
    Notes: string
    Password: string
    Resource?: string
    RemainedDay: number
    IfUseMasConfig?: boolean
    SeriesNumb: string
    Server: string
    Stage: string
    StageMode: string
    Stage_1: string
    Stage_2: string
    Stage_3: string
    Stage_Remain: string
    Status: boolean
    Tag?: string | null // 用户标签列表（JSON字符串，TagItem的dict列表）
  }
  Notify: {
    Enabled: boolean
    IfSendMail: boolean
    IfSendSixStar: boolean
    IfSendStatistic: boolean
    IfServerChan: boolean
    ServerChanChannel: string
    ServerChanKey: string
    ServerChanTag: string
    ToAddress: string
  }
  Task: {
    IfRoguelike: boolean
    IfInfrast: boolean
    IfFight: boolean
    IfMall: boolean
    IfAward: boolean
    IfReclamation: boolean
    IfRecruit: boolean
    IfStartUp: boolean
    Queue?: unknown
    IfActivityFirst?: boolean
    ActivityStageIndex?: number
    ActivityMedicineNumb?: number
    IfDepotMaintain?: boolean
    DepotMaintainPlans?: string
    SanityTaskType?: MaaEndTaskConfig['SanityTaskType']
    OperatorProgression?: MaaEndTaskConfig['OperatorProgression']
    WeaponProgression?: MaaEndTaskConfig['WeaponProgression']
    CrisisDrills?: MaaEndTaskConfig['CrisisDrills']
    RewardsSetOption?: MaaEndTaskConfig['RewardsSetOption']
    AutoEssenceSpecifiedLocation?: MaaEndTaskConfig['AutoEssenceSpecifiedLocation']
  }
  QFluentWidgets: {
    ThemeColor: string
    ThemeMode: string
  }
}

// API响应类型
export interface AddScriptResponse {
  code: number
  status: string
  message: string
  scriptId: string
  data:
    | MAAScriptConfig
    | GeneralScriptConfig
    | OkwwScriptConfig
    | OkNteScriptConfig
    | SRCScriptConfig
    | MaaEndScriptConfig
    | M9AScriptConfig
    | MaaFWScriptConfig
    | HSRScriptConfig
    | BetterGIScriptConfig
}

// 脚本索引项
export interface ScriptIndexItem {
  uid: string
  type:
    | 'MaaConfig'
    | 'GeneralConfig'
    | 'OkwwConfig'
    | 'OkNteConfig'
    | 'SrcConfig'
    | 'MaaEndConfig'
    | 'M9AConfig'
    | 'MaaFWConfig'
    | 'HSRConfig'
    | 'BetterGIConfig'
}

// 获取脚本API响应
export interface GetScriptsResponse {
  code: number
  status: string
  message: string
  index: ScriptIndexItem[]
  data: Record<
    string,
    | MAAScriptConfig
    | GeneralScriptConfig
    | OkwwScriptConfig
    | OkNteScriptConfig
    | SRCScriptConfig
    | MaaEndScriptConfig
    | M9AScriptConfig
    | MaaFWScriptConfig
    | HSRScriptConfig
    | BetterGIScriptConfig
  >
}

// 脚本详情（用于前端展示）
export interface ScriptDetail {
  uid: string
  type: ScriptType
  name: string
  config:
    | MaaConfig
    | GeneralConfig
    | OkwwConfig
    | OkNteConfig
    | SrcConfig
    | MaaEndConfig
    | M9AConfig
    | MaaFWScriptConfig
    | HSRConfig
    | BetterGIConfig
  users?: User[]
  createTime?: string
}

// 删除脚本API响应
export interface DeleteScriptResponse {
  code: number
  status: string
  message: string
}

// M9A 任务选项类型
export interface M9ATaskOption {
  name: string
  index: number
  sub_options?: M9ATaskOption[]
  input_values?: Record<string, string | number>
  selected_cases?: string[]
}

// M9A 任务队列项类型
export interface M9ATaskQueueItem {
  name: string
  options: M9ATaskOption[]
}

// 更新脚本API响应
export interface UpdateScriptResponse {
  code: number
  status: string
  message: string
}
