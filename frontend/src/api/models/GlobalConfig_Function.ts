/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GlobalConfig_Function = {
  /**
   * 历史记录保留时间, 0表示永久保存
   */
  HistoryRetentionTime?: 7 | 15 | 30 | 60 | 90 | 180 | 365 | 0 | null
  /**
   * 允许休眠
   */
  IfAllowSleep?: boolean | null
  /**
   * 静默模式
   */
  IfSilence?: boolean | null
  /**
   * 模拟器老板键
   */
  BossKey?: string | null
  /**
   * 同意哔哩哔哩用户协议
   */
  IfAgreeBilibili?: boolean | null
  /**
   * 跳过Mumu模拟器启动广告
   */
  IfSkipMumuSplashAds?: boolean | null
}
