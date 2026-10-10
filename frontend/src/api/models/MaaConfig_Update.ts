/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaConfig_Update = {
  /**
   * 是否接管 MAA 本体与资源更新（关=完全由 MAA 自行处理）
   */
  TakeoverEnabled?: boolean | null
  /**
   * 本脚本的 Mirror 酱 CDK（留空回退 MAS 全局配置）
   */
  MirrorChyanCDK?: string | null
}
