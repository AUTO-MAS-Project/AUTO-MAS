/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GetStageIn = {
  /**
   * 选择的日期类型, Today为当天, ALL为包含当天未开放关卡在内的所有项
   */
  type: GetStageIn.type
}
export namespace GetStageIn {
  /**
   * 选择的日期类型, Today为当天, ALL为包含当天未开放关卡在内的所有项
   */
  export enum type {
    TODAY = 'Today',
    ALL = 'ALL',
    MONDAY = 'Monday',
    TUESDAY = 'Tuesday',
    WEDNESDAY = 'Wednesday',
    THURSDAY = 'Thursday',
    FRIDAY = 'Friday',
    SATURDAY = 'Saturday',
    SUNDAY = 'Sunday',
  }
}
