/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HistoryData } from '@/api'

export type HistoryDataGetOut = {
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
   * 历史记录数据
   */
  data: HistoryData
}
