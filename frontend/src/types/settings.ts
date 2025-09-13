// 设置相关类型定义
export interface SettingsData {
  UI: {
    IfShowTray: boolean
    IfToTray: boolean
  }
  Function: {
    BossKey: string
    HistoryRetentionTime: number
    IfAgreeBilibili: boolean
    IfAllowSleep: boolean
    IfSilence: boolean
    IfSkipMumuSplashAds: boolean
  }
  Notify: {
    SendTaskResultTime: string
    IfSendStatistic: boolean
    IfSendSixStar: boolean
    IfPushPlyer: boolean
    IfSendMail: boolean
    SMTPServerAddress: string
    AuthorizationCode: string
    FromAddress: string
    ToAddress: string
    IfServerChan: boolean
    ServerChanKey: string
    ServerChanChannel: string
    ServerChanTag: string
    IfCompanyWebHookBot: boolean
    CompanyWebHookBotUrl: string
  }
  Update: {
    IfAutoUpdate: boolean
    Source: string
    ProxyAddress: string
    MirrorChyanCDK: string
  }
  Start: {
    IfSelfStart: boolean
    IfMinimizeDirectly: boolean
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
