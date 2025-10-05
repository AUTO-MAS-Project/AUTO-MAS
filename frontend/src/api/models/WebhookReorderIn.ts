/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WebhookReorderIn = {
  /**
   * 所属脚本ID, 获取全局设置的Webhook数据时无需携带
   */
  scriptId?: string | null
  /**
   * 所属用户ID, 获取全局设置的Webhook数据时无需携带
   */
  userId?: string | null
  /**
   * Webhook ID列表, 按新顺序排列
   */
  indexList: Array<string>
}
