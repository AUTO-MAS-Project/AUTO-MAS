// 脚本类型定义
import type {
  HSRConfig,
  HSRConfig_TaskMapping,
  HSRUserConfig,
  MaaConfig,
  GeneralConfig,
  OkwwConfig,
  OkNteConfig,
  SrcConfig,
  MaaEndConfig,
  M9AConfig,
} from '@/api'
import type {
  AutoEssenceLocation,
  MaaEndTaskSwitch,
  ProtocolSpaceTaskValue,
  RewardSetOption,
  SanityTaskType,
} from '@/utils/maaEndProtocolSpace'

export type ScriptType = 'MAA' | 'General' | 'Okww' | 'OkNte' | 'SRC' | 'MaaEnd' | 'M9A' | 'HSR'

export type OkwwScriptConfig = OkwwConfig
export type OkNteScriptConfig = OkNteConfig
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
  }
  SubConfigsInfo: {
    UserData: {
      instances: any[]
    }
  }
}

// HSR 脚本配置（后端已通过 HSRConfig OpenAPI 暴露类型）
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
  available: Set<'M7A' | 'SRA'>,
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
    | HSRConfig
  users: User[]
}

// 用户配置
export interface User {
  id: string
  name: string
  Data: {
    IfPassCheck: boolean
    LastProxyDate: string
    LastSklandDate: string
    ProxyTimes: number
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
    | HSRScriptConfig
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
    | OkNteScriptConfig
    | SRCScriptConfig
    | MaaEndScriptConfig
    | M9AScriptConfig
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
    | OkNteConfig
    | SrcConfig
    | MaaEndConfig
    | M9AConfig
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
