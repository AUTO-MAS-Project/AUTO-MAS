/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QueueItemGetIn = {
    /**
     * 所属队列ID
     */
    queueId: string;
    /**
     * 队列项ID, 未携带时表示获取所有队列项数据
     */
    queueItemId?: (string | null);
};

