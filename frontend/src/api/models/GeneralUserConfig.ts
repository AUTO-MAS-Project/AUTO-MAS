/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig_Data, GeneralUserConfig_Info, GeneralUserConfig_Notify } from '@/api'

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
