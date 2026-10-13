/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CollectionOrderItem } from './CollectionOrderItem';
import type { QueueEntry_Output } from './QueueEntry_Output';
export type QueueGetOut = {
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
     * 队列顺序
     */
    order?: Array<CollectionOrderItem>;
    /**
     * 队列数据，key 为 uid
     */
    data?: Record<string, QueueEntry_Output>;
};

