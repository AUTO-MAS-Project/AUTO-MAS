/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig } from './GeneralUserConfig'
import type { MaaUserConfig } from './MaaUserConfig'
import type { UserIndexItem } from './UserIndexItem'
export type UserGetOut = {
  /**
   * 状态码
   */
  code?: number
  /**
   * 操作状态
   */
  status?: string
  /**
   * 操作消息
   */
  message?: string
  /**
   * 用户索引列表
   */
  index: Array<UserIndexItem>
  /**
   * 用户数据字典, key来自于index列表的uid
   */
  data: Record<string, MaaUserConfig | GeneralUserConfig>
}
