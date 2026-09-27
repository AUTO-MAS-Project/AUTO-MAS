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
     * 编辑租约令牌
     */
    editLeaseToken?: (string | null);
    /**
     * 进入编辑时的基础指纹
     */
    baseVersion?: (string | null);
    /**
     * 队列项ID列表, 按新顺序排列
     */
    indexList: Array<string>;
};

