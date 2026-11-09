/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueConfig_Cycle = {
    /**
     * 队列循环触发间隔，单位分钟
     */
    IntervalMinutes?: (number | null);
    /**
     * 上次循环成功提交时间；为空时启用循环立即到期
     */
    readonly LastRunAt?: (string | null);
    /**
     * 下次循环触发时间，由上次触发时间和间隔计算
     */
    readonly NextRunAt?: (string | null);
};

