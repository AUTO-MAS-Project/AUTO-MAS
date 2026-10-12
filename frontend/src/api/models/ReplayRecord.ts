/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ReplayRecord = {
    /**
     * 回放唯一标识
     */
    replayId: string;
    /**
     * 调度任务标识
     */
    taskId?: (string | null);
    /**
     * 脚本标识
     */
    scriptId?: (string | null);
    /**
     * 账号标识
     */
    userId?: (string | null);
    /**
     * 脚本名称
     */
    scriptName?: string;
    /**
     * 账号名称
     */
    userName?: string;
    /**
     * 失败时间
     */
    failedAt: string;
    /**
     * 失败原因
     */
    reason: string;
    /**
     * MAS 保存的回放副本
     */
    filePath?: string;
    /**
     * 本轮关联历史记录
     */
    historyPaths?: Array<string>;
};
