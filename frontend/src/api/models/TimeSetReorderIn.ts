/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TimeSetReorderIn = {
    /**
     * 所属队列 ID
     */
    queueId: string;
    /**
     * 按新顺序排列的定时项 UID 列表
     */
    indexList: Array<string>;
};

