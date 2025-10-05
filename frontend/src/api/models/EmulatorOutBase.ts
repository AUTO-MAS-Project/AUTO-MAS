/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type EmulatorOutBase = {
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
   * 模拟器UUID
   */
  emulator_uuid: string
  /**
   * 模拟器信息
   */
  emulator_data: Record<string, any>
}
