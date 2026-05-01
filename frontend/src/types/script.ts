// 脚本类型定义
import type { MaaConfig, GeneralConfig, SrcConfig, MaaEndConfig } from '@/api'
import type { SchemaDefinition } from './schemaForm'

export type ScriptType = string

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
    ControllerType: 'Win32-Window' | 'Win32-Window-Background' | 'Win32-Front' | 'ADB' | null
    Path: string
    Arguments: string
    WaitTime: number
    EmulatorId: string
    EmulatorIndex: string
    CloseOnFinish: boolean
  }
}

// 脚本基础信息
export interface Script {
  id: string
  type: ScriptType
  name: string
  config: MaaConfig | GeneralConfig | SrcConfig | MaaEndConfig | Record<string, any>
  users: User[]
  schema?: SchemaDefinition
  userSchema?: SchemaDefinition
  editorKind?: string
  supportedModes?: string[]
  icon?: string | null
  docsUrl?: string | null
  displayName?: string
  isBuiltin?: boolean
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
  data: MAAScriptConfig | GeneralScriptConfig | SRCScriptConfig | MaaEndScriptConfig
}

// 脚本索引项
export interface ScriptIndexItem {
  uid: string
  type: 'MaaConfig' | 'GeneralConfig' | 'SrcConfig' | 'MaaEndConfig'
}

// 获取脚本API响应
export interface GetScriptsResponse {
  code: number
  status: string
  message: string
  index: ScriptIndexItem[]
  data: Record<string, MAAScriptConfig | GeneralScriptConfig | SRCScriptConfig | MaaEndScriptConfig>
}

// 脚本详情（用于前端展示）
export interface ScriptDetail {
  uid: string
  type: ScriptType
  name: string
  config: MaaConfig | GeneralConfig | SrcConfig | MaaEndConfig
  users?: User[]
  createTime?: string
}

// 删除脚本API响应
export interface DeleteScriptResponse {
  code: number
  status: string
  message: string
}

// 更新脚本API响应
export interface UpdateScriptResponse {
  code: number
  status: string
  message: string
}
