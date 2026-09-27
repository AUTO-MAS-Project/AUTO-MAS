/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueConfig } from './QueueConfig';
export type QueueUpdateIn = {
    /**
     * 编辑租约令牌
     */
    editLeaseToken?: (string | null);
    /**
     * 进入编辑时的基础指纹
     */
    baseVersion?: (string | null);
    /**
     * 队列ID
     */
    queueId: string;
    /**
     * 队列更新数据
     */
    data: QueueConfig;
};

