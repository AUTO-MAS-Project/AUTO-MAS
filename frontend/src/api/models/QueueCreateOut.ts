/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueEntry_Output } from './QueueEntry_Output';
export type QueueCreateOut = {
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
     * 新队列 ID
     */
    queueId?: string;
    /**
     * 队列配置
     */
    data?: QueueEntry_Output;
};

