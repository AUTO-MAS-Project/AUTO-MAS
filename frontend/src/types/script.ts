// 脚本类型定义
export type ScriptType = 'MAA' | 'General'

// MAA脚本配置
export interface MAAScriptConfig {
  Info: {
    Name: string
    Path: string
  }
  Run: {
    ADBSearchRange: number
    AnnihilationTimeLimit: number
    AnnihilationWeeklyLimit: boolean
    ProxyTimesLimit: number
    RoutineTimeLimit: number
    RunTimesLimit: number
    TaskTransitionMethod: string
  }
  SubConfigsInfo: {
    UserData: {
      instances: any[]
    }
  }
}

// General脚本配置
export interface GeneralScriptConfig {
  Game: {
    Arguments: string
    Enabled: boolean
    IfForceClose: boolean
    Path: string
    Style: string
    WaitTime: number
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
  config: MAAScriptConfig | GeneralScriptConfig
  users: User[]
}

// 用户配置
export interface User {
  id: string
  name: string
  Data: {
    CustomInfrastPlanIndex: string
    IfPassCheck: boolean
    LastAnnihilationDate: string
    LastProxyDate: string
    LastSklandDate: string
    ProxyTimes: number
  }
  Info: {
    Annihilation: string
    Id: string
    IfSkland: boolean
    InfrastMode: string
    MedicineNumb: number
    Mode: string
    Name: string
    Notes: string
    Password: string
    RemainedDay: number
    Routine: boolean
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
    CompanyWebHookBotUrl: string
    Enabled: boolean
    IfCompanyWebHookBot: boolean
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
    IfAutoRoguelike: boolean
    IfBase: boolean
    IfCombat: boolean
    IfMall: boolean
    IfMission: boolean
    IfReclamation: boolean
    IfRecruiting: boolean
    IfWakeUp: boolean
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
  config: MAAScriptConfig | GeneralScriptConfig
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
