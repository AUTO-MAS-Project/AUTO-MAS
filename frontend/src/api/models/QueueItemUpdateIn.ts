/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueItemEntry_Input } from './QueueItemEntry_Input';
export type QueueItemUpdateIn = {
    /**
     * 所属队列 ID
     */
    queueId: string;
    /**
     * 队列项 ID
     */
    queueItemId: string;
    /**
     * 队列项补丁（文档形状）
     */
    data: QueueItemEntry_Input;
};

