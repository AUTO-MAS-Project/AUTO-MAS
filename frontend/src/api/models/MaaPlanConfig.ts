/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaPlanConfig_Info, MaaPlanConfig_Item } from '@/api'

export type MaaPlanConfig = {
  /**
   * 基础信息
   */
  Info?: MaaPlanConfig_Info | null
  /**
   * 全局
   */
  ALL?: MaaPlanConfig_Item | null
  /**
   * 周一
   */
  Monday?: MaaPlanConfig_Item | null
  /**
   * 周二
   */
  Tuesday?: MaaPlanConfig_Item | null
  /**
   * 周三
   */
  Wednesday?: MaaPlanConfig_Item | null
  /**
   * 周四
   */
  Thursday?: MaaPlanConfig_Item | null
  /**
   * 周五
   */
  Friday?: MaaPlanConfig_Item | null
  /**
   * 周六
   */
  Saturday?: MaaPlanConfig_Item | null
  /**
   * 周日
   */
  Sunday?: MaaPlanConfig_Item | null
}
