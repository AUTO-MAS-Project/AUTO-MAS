/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueItem_Data = {
    /**
     * 上次循环开始时间
     */
    LastCycleStartedAt?: (string | null);
    /**
     * 上次循环完成时间
     */
    LastCycleFinishedAt?: (string | null);
    /**
     * 本轮循环运行ID
     */
    CycleRunId?: (string | null);
    /**
     * 循环运行持久化状态
     */
    CycleState?: ('idle' | 'running' | 'succeeded' | 'failed' | 'cancelled' | null);
    /**
     * 队列项循环状态修订号
     */
    CycleRevision?: (number | null);
    /**
     * 最近循环运行结果
     */
    CycleResult?: (string | null);
    /**
     * 最近循环运行错误
     */
    CycleError?: (string | null);
    /**
     * 循环状态更新时间
     */
    CycleUpdatedAt?: (string | null);
};

