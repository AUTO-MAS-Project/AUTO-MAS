/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TimeSet } from '@/api'

export type TimeSetUpdateIn = {
  /**
   * 所属队列ID
   */
  queueId: string
  /**
   * 时间设置ID
   */
  timeSetId: string
  /**
   * 时间设置更新数据
   */
  data: TimeSet
}
