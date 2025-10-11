/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueConfig } from './QueueConfig';
import type { QueueIndexItem } from './QueueIndexItem';
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
     * 队列索引列表
     */
    index: Array<QueueIndexItem>;
    /**
     * 队列数据字典, key来自于index列表的uid
     */
    data: Record<string, QueueConfig>;
};

