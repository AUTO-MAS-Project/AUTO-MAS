// 设置相关类型定义
export interface SettingsData {
  Function: {
    BossKey: string
    HistoryRetentionTime: number
    HomeImageMode: string
    IfAgreeBilibili: boolean
    IfAllowSleep: boolean
    IfSilence: boolean
    IfSkipMumuSplashAds: boolean
    UnattendedMode: boolean
  }
  Notify: {
    AuthorizationCode: string
    CompanyWebHookBotUrl: string
    FromAddress: string
    IfCompanyWebHookBot: boolean
    IfPushPlyer: boolean
    IfSendMail: boolean
    IfSendSixStar: boolean
    IfSendStatistic: boolean
    IfServerChan: boolean
    SMTPServerAddress: string
    SendTaskResultTime: string
    ServerChanChannel: string
    ServerChanKey: string
    ServerChanTag: string
    ToAddress: string
  }
  Update: {
    IfAutoUpdate: boolean
    MirrorChyanCDK: string
    ProxyAddress: string
    ProxyUrlList: string[]
    ThreadNumb: number
    UpdateType: string
  }
  Start: {
    IfMinimizeDirectly: boolean
    IfSelfStart: boolean
  }
  UI: {
    IfShowTray: boolean // 常驻显示托盘
    IfToTray: boolean   // 最小化到托盘
    location: string
    maximized: boolean
    size: string
  }
  Voice: {
    Enabled: boolean
    Type: string
  }
}

// 获取设置API响应
export interface GetSettingsResponse {
  code: number
  status: string
  message: string
  data: SettingsData
}

// 更新设置API响应
export interface UpdateSettingsResponse {
  code: number
  status: string
  message: string
}
