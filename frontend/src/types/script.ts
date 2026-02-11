// 脚本类型定义
import type { MaaConfig, GeneralConfig } from '@/api'

export type ScriptType = 'MAA' | 'General'

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

// 脚本基础信息
export interface Script {
  id: string
  type: ScriptType
  name: string
  config: MaaConfig | GeneralConfig
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
  data: MAAScriptConfig | GeneralScriptConfig
}

// 脚本索引项
export interface ScriptIndexItem {
  uid: string
  type: 'MaaConfig' | 'GeneralConfig'
}

// 获取脚本API响应
export interface GetScriptsResponse {
  code: number
  status: string
  message: string
  index: ScriptIndexItem[]
  data: Record<string, MAAScriptConfig | GeneralScriptConfig>
}

// 脚本详情（用于前端展示）
export interface ScriptDetail {
  uid: string
  type: ScriptType
  name: string
  config: MaaConfig | GeneralConfig
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
