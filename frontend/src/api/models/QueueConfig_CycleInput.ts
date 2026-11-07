/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueConfig_CycleInput = {
    /**
     * 队列循环触发间隔，单位分钟
     */
    IntervalMinutes?: (number | null);
    /**
     * 下次循环触发时间，由上次触发时间和间隔计算
     */
    readonly NextRunAt?: (string | null);
    /**
     * 重置循环计时，将上次循环触发时间设为现在
     */
    ResetTimer?: (boolean | null);
};

