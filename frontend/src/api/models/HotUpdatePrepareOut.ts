/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 后端热更准备响应
 */
export type HotUpdatePrepareOut = {
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
     * 是否准入
     */
    ready?: boolean;
    /**
     * 未就绪的机读原因
     */
    reason?: ('busy' | 'scheduledSoon' | 'paused' | 'closing' | null);
    /**
     * 最近的定时任务时刻（ISO 格式）
     */
    nextScheduledTime?: (string | null);
};

