/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueItem } from './QueueItem'
export type QueueItemCreateOut = {
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
   * 新创建的队列项ID
   */
  queueItemId: string
  /**
   * 队列项配置数据
   */
  data: QueueItem
}
