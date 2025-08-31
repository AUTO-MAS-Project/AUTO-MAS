/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueItemReorderIn = {
    /**
     * 所属队列ID
     */
    queueId: string;
    /**
     * 队列项ID列表, 按新顺序排列
     */
    indexList: Array<string>;
};

