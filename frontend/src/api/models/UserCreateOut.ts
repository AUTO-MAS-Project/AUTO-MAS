/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig, MaaUserConfig } from '@/api'

export type UserCreateOut = {
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
   * 新创建的用户ID
   */
  userId: string
  /**
   * 用户配置数据
   */
  data: MaaUserConfig | GeneralUserConfig
}
