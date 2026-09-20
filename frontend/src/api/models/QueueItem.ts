/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueItem_Data } from './QueueItem_Data';
import type { QueueItem_Info } from './QueueItem_Info';
import type { QueueItem_Schedule } from './QueueItem_Schedule';
export type QueueItem = {
    /**
     * 队列项
     */
    Info?: (QueueItem_Info | null);
    /**
     * 队列项的循环调度配置
     */
    Schedule?: (QueueItem_Schedule | null);
    /**
     * 队列项的循环运行数据
     */
    Data?: (QueueItem_Data | null);
};

