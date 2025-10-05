/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueConfig_Info = {
  /**
   * 队列名称
   */
  Name?: string | null
  /**
   * 是否启用定时
   */
  TimeEnabled?: boolean | null
  /**
   * 是否启动时运行
   */
  StartUpEnabled?: boolean | null
  /**
   * 完成后操作
   */
  AfterAccomplish?:
    | 'NoAction'
    | 'KillSelf'
    | 'Sleep'
    | 'Hibernate'
    | 'Shutdown'
    | 'ShutdownForce'
    | null
}
