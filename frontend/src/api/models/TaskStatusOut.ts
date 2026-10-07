/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 按 taskId 单点查询一个任务的状态, 不携带日志。
 */
export type TaskStatusOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 任务状态; running 为运行中, 其余为终态
     */
    status: TaskStatusOut.status;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 任务 ID
     */
    taskId: string;
    /**
     * 任务结果描述
     */
    detail?: (string | null);
    /**
     * 任务错误信息
     */
    error?: (string | null);
    /**
     * 任务模式
     */
    mode?: ('AutoProxy' | 'ScriptConfig' | 'Update' | null);
    /**
     * 是否为循环运行任务
     */
    isCycle?: boolean;
    /**
     * 调度队列 ID
     */
    queueId?: (string | null);
    /**
     * 脚本 ID
     */
    scriptId?: (string | null);
    /**
     * 用户 ID
     */
    userId?: (string | null);
    /**
     * 任务是否正在停止
     */
    stopping?: boolean;
    /**
     * 任务结束时间, 格式为YYYY-MM-DD HH:MM:SS, 运行中为空
     */
    finishedAt?: (string | null);
};
export namespace TaskStatusOut {
    /**
     * 任务状态; running 为运行中, 其余为终态
     */
    export enum status {
        RUNNING = 'running',
        SUCCESS = 'success',
        ERROR = 'error',
        CANCELLED = 'cancelled',
    }
}

