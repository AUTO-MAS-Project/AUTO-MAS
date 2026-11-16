/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueItemInput } from './QueueItemInput';
export type QueueItemUpdateIn = {
    /**
     * 所属队列ID
     */
    queueId: string;
    /**
     * 队列项ID
     */
    queueItemId: string;
    /**
     * 队列项更新数据
     */
    data: QueueItemInput;
};

