/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueItemEntry_Output } from './QueueItemEntry_Output';
export type QueueItemCreateOut = {
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
     * 新队列项 ID
     */
    queueItemId?: string;
    /**
     * 队列项配置
     */
    data?: QueueItemEntry_Output;
};

