/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueItem } from './QueueItem';
import type { QueueItemIndexItem } from './QueueItemIndexItem';
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
     * 队列项索引列表
     */
    index: Array<QueueItemIndexItem>;
    /**
     * 队列项数据字典, key来自于index列表的uid
     */
    data: Record<string, QueueItem>;
};

