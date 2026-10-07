/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 统一任务终态结果契约: 所有任务类型复用同一形状, 供停止响应与结果查询接口返回。
 */
export type TaskOutcome = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 任务 ID
     */
    taskId: string;
    /**
     * 机器可读的最终业务结果
     */
    outcome: TaskOutcome.outcome;
    /**
     * 机器可读的结果原因, 无原因为空
     */
    reason?: (string | null);
    /**
     * 结果作用范围, 例如 native_config
     */
    scope?: (string | null);
    /**
     * 用户数据是否仍然保留
     */
    dataPreserved?: boolean;
    /**
     * 该操作是否可安全重试
     */
    retryable?: boolean;
    /**
     * 前端文案 key
     */
    messageKey?: (string | null);
    /**
     * 任务结束时间, 格式为YYYY-MM-DD HH:MM:SS, 任务未结束为空
     */
    finishedAt?: (string | null);
};
export namespace TaskOutcome {
    /**
     * 机器可读的最终业务结果
     */
    export enum outcome {
        SAVED = 'saved',
        DISCARDED = 'discarded',
        FAILED = 'failed',
        CANCELLED = 'cancelled',
        COMPLETED = 'completed',
        COMPLETED_WITHOUT_WRITE = 'completed_without_write',
        UNKNOWN = 'unknown',
    }
}
