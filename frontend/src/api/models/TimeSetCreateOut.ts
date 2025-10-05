/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TimeSet } from './TimeSet'
export type TimeSetCreateOut = {
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
   * 新创建的时间设置ID
   */
  timeSetId: string
  /**
   * 时间设置配置数据
   */
  data: TimeSet
}
