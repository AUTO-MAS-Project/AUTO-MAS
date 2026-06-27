/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRConfig_Run = {
    /**
     * 失败任务最大尝试次数
     */
    RunTimesLimit?: (number | null);
    /**
     * 日常任务超时限制（分钟）
     */
    DailyTimeLimit?: (number | null);
    /**
     * 周常任务超时限制（分钟）
     */
    WeeklyTimeLimit?: (number | null);
    /**
     * 月常任务超时限制（分钟）
     */
    MonthlyTimeLimit?: (number | null);
    /**
     * 低性能兼容模式（仅三月七差分宇宙）
     */
    LowPerformanceMode?: (boolean | null);
};

