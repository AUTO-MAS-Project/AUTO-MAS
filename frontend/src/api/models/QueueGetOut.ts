/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
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
    index: Array<Record<string, string>>;
    /**
     * 队列列表或单个队列数据
     */
    data: Record<string, any>;
};

