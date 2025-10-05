/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ScriptIndexItem = {
  /**
   * 唯一标识符
   */
  uid: string
  /**
   * 配置类型
   */
  type: ScriptIndexItem.type
}
export namespace ScriptIndexItem {
  /**
   * 配置类型
   */
  export enum type {
    MAA_CONFIG = 'MaaConfig',
    GENERAL_CONFIG = 'GeneralConfig',
  }
}
