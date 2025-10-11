/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 更新模拟器配置响应
 */
export type EmulatorUpdateOut = {
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
   * 更正后的模拟器路径
   */
  correctedPath?: string | null
  /**
   * 检测到的模拟器类型
   */
  detectedType?: string | null
}
