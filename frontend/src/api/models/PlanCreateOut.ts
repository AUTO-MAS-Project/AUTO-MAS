/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaPlanConfig } from './MaaPlanConfig'
export type PlanCreateOut = {
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
   * 新创建的计划ID
   */
  planId: string
  /**
   * 计划配置数据
   */
  data: MaaPlanConfig
}
