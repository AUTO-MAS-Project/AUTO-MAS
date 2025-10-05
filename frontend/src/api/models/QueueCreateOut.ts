/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueConfig } from './QueueConfig'
export type QueueCreateOut = {
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
   * 新创建的队列ID
   */
  queueId: string
  /**
   * 队列配置数据
   */
  data: QueueConfig
}
