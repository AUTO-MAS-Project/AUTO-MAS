/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmulatorSearchResult } from '@/api'

/**
 * 模拟器搜索响应
 */
export type EmulatorSearchOut = {
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
   * 搜索到的模拟器列表
   */
  emulators?: Array<EmulatorSearchResult>
}
