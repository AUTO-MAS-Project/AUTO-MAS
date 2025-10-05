/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig_Data } from './GeneralUserConfig_Data'
import type { GeneralUserConfig_Info } from './GeneralUserConfig_Info'
import type { GeneralUserConfig_Notify } from './GeneralUserConfig_Notify'
export type GeneralUserConfig = {
  /**
   * 用户信息
   */
  Info?: GeneralUserConfig_Info | null
  /**
   * 用户数据
   */
  Data?: GeneralUserConfig_Data | null
  /**
   * 单独通知
   */
  Notify?: GeneralUserConfig_Notify | null
}
