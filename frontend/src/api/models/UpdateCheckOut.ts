/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type UpdateCheckOut = {
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
   * 是否需要更新前端
   */
  if_need_update: boolean
  /**
   * 最新前端版本号
   */
  latest_version: string
  /**
   * 版本更新信息字典
   */
  update_info: Record<string, Array<string>>
}
