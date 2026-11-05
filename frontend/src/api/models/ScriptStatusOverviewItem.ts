/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 托管配置与持久化历史的只读概览，不包含运行任务状态。
 */
export type ScriptStatusOverviewItem = {
    scriptId: string;
    scriptType: string;
    scheduled?: boolean;
    lastRunAt?: (string | null);
    lastFailed?: boolean;
};

