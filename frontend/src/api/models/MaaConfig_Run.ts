/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaConfig_Run = {
    /**
     * 简洁任务间切换方式
     */
    TaskTransitionMethod?: ('NoAction' | 'ExitGame' | 'ExitEmulator' | null);
    /**
     * 每日代理次数限制
     */
    ProxyTimesLimit?: (number | null);
    /**
     * ADB端口搜索范围
     */
    ADBSearchRange?: (number | null);
    /**
     * 重试次数限制
     */
    RunTimesLimit?: (number | null);
    /**
     * 剿灭超时限制
     */
    AnnihilationTimeLimit?: (number | null);
    /**
     * 日常超时限制
     */
    RoutineTimeLimit?: (number | null);
    /**
     * 剿灭每周仅代理至上限
     */
    AnnihilationWeeklyLimit?: (boolean | null);
};

