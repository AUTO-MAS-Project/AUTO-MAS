/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type {
  GlobalConfig_Function,
  GlobalConfig_Notify,
  GlobalConfig_Start,
  GlobalConfig_UI,
  GlobalConfig_Update,
  GlobalConfig_Voice,
} from '@/api'

export type GlobalConfig = {
  /**
   * 功能相关配置
   */
  Function?: GlobalConfig_Function | null
  /**
   * 语音相关配置
   */
  Voice?: GlobalConfig_Voice | null
  /**
   * 启动相关配置
   */
  Start?: GlobalConfig_Start | null
  /**
   * 界面相关配置
   */
  UI?: GlobalConfig_UI | null
  /**
   * 通知相关配置
   */
  Notify?: GlobalConfig_Notify | null
  /**
   * 更新相关配置
   */
  Update?: GlobalConfig_Update | null
}
