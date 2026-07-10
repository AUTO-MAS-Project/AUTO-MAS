// 脚本类型定义
import type {
  HSRConfig,
  HSRConfig_TaskMapping,
  MaaConfig,
  GeneralConfig,
  OkwwConfig,
  SrcConfig,
  MaaEndConfig,
  M9AConfig,
  MaaFWConfig as ApiMaaFWConfig,
} from '@/api'
import type {
  AutoEssenceLocation,
  MaaEndTaskSwitch,
  ProtocolSpaceTaskValue,
  RewardSetOption,
  SanityTaskType,
} from '@/utils/maaEndProtocolSpace'
import type { SchemaDefinition } from './schemaForm'

/**
 * 内建脚本类型键。插件系统引入后，脚本类型键是开放集合（插件可注册任意
 * type_key），因此 ScriptType 为 string；BuiltinScriptType 保留内建类型的
 * 字面量枚举供需要穷举内建类型的场景使用。
 */
export type BuiltinScriptType =
  | 'MAA'
  | 'General'
  | 'Okww'
  | 'OkScript'
  | 'Okef'
  | 'SRC'
  | 'MaaEnd'
  | 'M9A'
  | 'MaaFW'
  | 'HSR'

export type ScriptType = string

export type OkwwScriptConfig = OkwwConfig
export interface OkefScriptConfig {
  Info: {
    Name: string
    ResourceName?: string
    ProjectLabel?: string
    RootPath: string
  }
  Script: Record<string, never>
  Game: {
    Enabled: boolean
    Path: string
    Arguments: string
    WaitTime: number
  }
  Run: {
    ProxyTimesLimit: number
    RunTimesLimit: number
    RunTimeLimit: number
  }
  SubConfigsInfo?: {
    UserData: {
      instances: any[]
    }
  }
}
export type OkScriptScriptConfig = OkefScriptConfig
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
    AnnihilationAvoidWaste: boolean
  }
  Emulator: {
    Id: string
    Index: string
  }
  SubConfigsInfo: {
    UserData: {
      instances: any[]
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
    ScriptPath: string
    SuccessLog: string
    UpdateConfigMode: string
  }
  SubConfigsInfo: {
    UserData: {
      instances: any[]
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
  }
  Game: {
    ControllerType: 'Win32-Front' | 'ADB' | null
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
      instances: any[]
    }
  }
}

// MaaFramework 项目脚本配置
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
    Path: string
    Arguments: string
    WaitTime: number
    CloseOnFinish: boolean
  }
  Update: {
    IfAutoUpdate: boolean
    Source: 'MirrorChyan'
    Channel: '' | 'stable' | 'beta'
    MirrorChyanCDK: string
  }
  Run: {
    ProxyTimesLimit: number
    RunTimesLimit: number
    RunTimeLimit: number
    WeeklyOnceTasks: string | string[]
    MonthlyOnceTasks: string | string[]
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
  }
  Task: {
    SelectedPreset: string
    TaskSnapshot: string | MaaFWTaskSnapshot
  }
  Device: {
    AdbAddress: string
    HWnd: number
    PlayCoverAddress: string
    PlayCoverUuid: string
  }
  Notify: {
    Enabled: boolean
    IfSendStatistic: boolean
    IfSendMail: boolean
    ToAddress: string
    IfServerChan: boolean
    ServerChanKey: string
    CustomWebhooks: Array<{
      id: string
      name: string
      url: string
      template: string
      enabled: boolean
      headers?: Record<string, string>
      method?: 'POST' | 'GET'
    }>
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
}

export interface MaaFWInterfacePreviewData {
  path: string
  project: MaaFWProjectInfo
  globalOption: string[]
  controlCapabilities: MaaFWControlCapabilitiesInfo
  controllers: MaaFWControllerInfo[]
  resources: MaaFWResourceInfo[]
  groups: MaaFWGroupInfo[]
  tasks: MaaFWTaskInfo[]
  options: MaaFWOptionInfo[]
  presets: MaaFWPresetInfo[]
  importCount: number
  agentCount: number
}

export interface MaaFWDesktopWindowInfo {
  hWnd: number
  className: string
  windowName: string
  controllerName: string
  controllerType: string
}

export interface MaaFWWindowPreviewData {
  path: string
  controllerName?: string | null
  windows: MaaFWDesktopWindowInfo[]
}

// HSR 脚本配置（后端已通过 HSRConfig OpenAPI 暴露类型）
export interface MaaFWAgentEnvInfo {
  childExec: string
  executable: string
  runtimeKind?: string | null
  isolatedVenvPath?: string | null
  fallbackReason?: string | null
}

export interface MaaFWAgentEnvPrepareData {
  path: string
  agentCount: number
  agents: MaaFWAgentEnvInfo[]
  logs: string[]
  status?: string
  message?: string
}

export type HSRScriptConfig = HSRConfig

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
    | OkefScriptConfig
    | SrcConfig
    | MaaEndConfig
    | M9AConfig
    | ApiMaaFWConfig
    | MaaFWScriptConfig
    | HSRConfig
    | Record<string, any>
  users: User[]
  schema?: SchemaDefinition
  userSchema?: SchemaDefinition
  editorKind?: string
  supportedModes?: string[]
  icon?: string | null
  docsUrl?: string | null
  displayName?: string
  isBuiltin?: boolean
  available?: boolean
  unavailableReason?: string | null
  createTime?: string
}

// 用户配置
export interface User {
  id: string
  name: string
  scriptId?: string
  type?: string
  schema?: SchemaDefinition
  config?: Record<string, any>
  Data: {
    IfPassCheck: boolean
    LastProxyDate: string
    LastPsychubeDate?: string
    LastLimboMonth?: string
    LastLucidscapeMonth?: string
    LastSklandDate: string
    ProxyTimes: number
    LastProxyStatus?: string
    LastTaskIndex?: number
  }
  Info: {
    Annihilation: string
    Id: string
    IfSkland: boolean
    InfrastMode: string
    InfrastName: string
    InfrastIndex: string
    MedicineNumb: number
    Mode: string
    Name: string
    SanityMode?: string
    Notes: string
    Password: string
    RemainedDay: number
    Controller?: string
    Resource?: string
    Account?: string
    EmulatorId?: string
    EmulatorIndex?: string | number
    SeriesNumb: string
    Server: string
    SklandToken: string
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
    CustomWebhooks: Array<{
      id: string
      name: string
      url: string
      template: string
      enabled: boolean
      headers?: Record<string, string>
      method?: 'POST' | 'GET'
    }>
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
    SanityTaskType?: MaaEndTaskConfig['SanityTaskType']
    OperatorProgression?: MaaEndTaskConfig['OperatorProgression']
    WeaponProgression?: MaaEndTaskConfig['WeaponProgression']
    CrisisDrills?: MaaEndTaskConfig['CrisisDrills']
    RewardsSetOption?: MaaEndTaskConfig['RewardsSetOption']
    AutoEssenceSpecifiedLocation?: MaaEndTaskConfig['AutoEssenceSpecifiedLocation']
    SelectedPreset?: string
    TaskSnapshot?: string | MaaFWTaskSnapshot
    TaskIndex?: number
    ExitOnFinish?: boolean
  }
  Device?: {
    AdbAddress?: string
    HWnd?: number
    PlayCoverAddress?: string
    PlayCoverUuid?: string
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
    | OkefScriptConfig
    | SRCScriptConfig
    | MaaEndScriptConfig
    | M9AScriptConfig
    | ApiMaaFWConfig
    | MaaFWScriptConfig
    | HSRScriptConfig
}

// 脚本索引项
export interface ScriptIndexItem {
  uid: string
  type:
    | 'MaaConfig'
    | 'GeneralConfig'
    | 'OkwwConfig'
    | 'OkefConfig'
    | 'SrcConfig'
    | 'MaaEndConfig'
    | 'M9AConfig'
    | 'MaaFWConfig'
    | 'HSRConfig'
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
    | OkefScriptConfig
    | SRCScriptConfig
    | MaaEndScriptConfig
    | M9AScriptConfig
    | ApiMaaFWConfig
    | MaaFWScriptConfig
    | HSRScriptConfig
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
    | OkefScriptConfig
    | SrcConfig
    | MaaEndConfig
    | M9AConfig
    | ApiMaaFWConfig
    | MaaFWScriptConfig
    | HSRConfig
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
