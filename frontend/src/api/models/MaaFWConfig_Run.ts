/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Run = {
    /**
     * 代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 运行次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 运行时间限制（分钟）
     */
    RunTimeLimit?: (number | null);
    /**
     * 每周正常完成一次后本周跳过的 MaaFW 任务名列表
     */
    WeeklyOnceTasks?: (string | null);
    /**
     * 每月正常完成一次后本月跳过的 MaaFW 任务名列表
     */
    MonthlyOnceTasks?: (string | null);
};

