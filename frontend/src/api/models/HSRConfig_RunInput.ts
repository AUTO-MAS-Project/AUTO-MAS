/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRConfig_RunInput = {
    /**
     * 日常任务超时限制（分钟）
     */
    DailyTimeLimit?: (number | null);
    /**
     * 低性能兼容模式（仅三月七差分宇宙使用，映射到 weekly_divergent_stable_mode）
     */
    LowPerformanceMode?: (boolean | null);
    /**
     * 代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 失败任务最大尝试次数
     */
    RunTimesLimit?: (number | null);
    /**
     * 周常任务超时限制（分钟）
     */
    WeeklyTimeLimit?: (number | null);
};

