// 自定义Webhook配置
export interface CustomWebhook {
  id: string
  name: string
  url: string
  template: string
  enabled: boolean
  headers?: Record<string, string>
  method?: 'POST' | 'GET'
}

// 设置相关类型定义
export interface SettingsData {
  UI: {
    IfShowTray: boolean
    IfToTray: boolean
  }
  Function: {
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
    IfSendKoishi: boolean
    KoishiServerAddress: string
    KoishiToken: string
    SMTPServerAddress: string
    AuthorizationCode: string
    FromAddress: string
    ToAddress: string
    IfServerChan: boolean
    ServerChanKey: string
    ServerChanChannel: string
    ServerChanTag: string
    CustomWebhooks: CustomWebhook[]
  }
  Update: {
    IfAutoUpdate: boolean
    Source: string
    Channel: string
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
