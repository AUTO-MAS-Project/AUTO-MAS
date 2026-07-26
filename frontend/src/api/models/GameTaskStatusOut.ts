/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GameTaskStatusOut = {
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
     * 任务是否仍在运行
     */
    running?: boolean;
    /**
     * 任务 UUID
     */
    taskId?: string;
    /**
     * 游戏 UUID
     */
    gameId?: string;
    action?: string;
    taskStatus?: ('running' | 'handed_off' | 'completed' | 'failed' | 'cancelled' | null);
    phase?: ('queued' | 'handoff' | 'download' | 'verify' | 'patch' | 'install' | 'awaiting_user' | 'completed' | 'failed' | 'cancelled' | null);
    percent?: number;
    downloaded?: number;
    total?: number;
    speed?: number;
    detail?: string;
    startedAt?: (string | null);
    updatedAt?: (string | null);
    finishedAt?: (string | null);
};

