/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CollectionOrderItem } from './CollectionOrderItem';
import type { QueueItemEntry_Output } from './QueueItemEntry_Output';
export type QueueItemGetOut = {
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
     * 队列项顺序
     */
    order?: Array<CollectionOrderItem>;
    /**
     * 队列项数据，key 为 uid
     */
    data?: Record<string, QueueItemEntry_Output>;
};

