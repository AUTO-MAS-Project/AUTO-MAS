/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkScriptConfig_Run = {
    /**
     * 每日代理次数上限，0 表示不限
     */
    ProxyTimesLimit?: (number | null);
    /**
     * 单次任务最多运行次数（含首次）
     */
    RunTimesLimit?: (number | null);
    /**
     * 单次运行时间上限（分钟），超时仍无完成标记即结束并判为无法确认完成
     */
    RunTimeLimit?: (number | null);
};

