/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type UserIndexItem = {
  /**
   * 唯一标识符
   */
  uid: string
  /**
   * 配置类型
   */
  type: UserIndexItem.type
}
export namespace UserIndexItem {
  /**
   * 配置类型
   */
  export enum type {
    MAA_USER_CONFIG = 'MaaUserConfig',
    GENERAL_USER_CONFIG = 'GeneralUserConfig',
  }
}
