/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SrcConfig_Run = {
    /**
     * 任务切换方式
     */
    TaskTransitionMethod?: ('ExitGame' | 'ExitEmulator' | null);
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
};

