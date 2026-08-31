/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWTaskSnapshot = {
    /**
     * 任务 name 顺序
     */
    taskOrder?: Array<string>;
    /**
     * 任务勾选状态
     */
    taskChecked?: Record<string, boolean>;
    /**
     * 任务选项值
     */
    taskOptions?: Record<string, Record<string, (string | Array<string> | Record<string, string>)>>;
};

