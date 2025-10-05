/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaUserConfig_Data } from './MaaUserConfig_Data'
import type { MaaUserConfig_Info } from './MaaUserConfig_Info'
import type { MaaUserConfig_Notify } from './MaaUserConfig_Notify'
import type { MaaUserConfig_Task } from './MaaUserConfig_Task'
export type MaaUserConfig = {
  /**
   * 基础信息
   */
  Info?: MaaUserConfig_Info | null
  /**
   * 用户数据
   */
  Data?: MaaUserConfig_Data | null
  /**
   * 任务列表
   */
  Task?: MaaUserConfig_Task | null
  /**
   * 单独通知
   */
  Notify?: MaaUserConfig_Notify | null
}
