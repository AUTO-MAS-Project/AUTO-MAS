/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWProjectUpdateJobData } from './MaaFWProjectUpdateJobData';
export type MaaFWProjectUpdateJobOut = {
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
     * 当前或最近一次手动更新的过程与结果
     */
    data?: MaaFWProjectUpdateJobData;
};

