/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TaskCreateIn = {
  /**
   * 目标任务ID, 设置类任务可选对应脚本ID或用户ID, 代理类任务可选对应队列ID或脚本ID
   */
  taskId: string
  /**
   * 任务模式
   */
  mode: TaskCreateIn.mode
}
export namespace TaskCreateIn {
  /**
   * 任务模式
   */
  export enum mode {
    AutoMode = '自动代理',
    ManualMode = '人工排查',
    SettingScriptMode = '设置脚本',
  }
}
