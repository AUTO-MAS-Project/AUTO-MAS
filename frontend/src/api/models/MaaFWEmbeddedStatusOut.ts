/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWEmbeddedStatusData } from './MaaFWEmbeddedStatusData';
export type MaaFWEmbeddedStatusOut = {
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
     * 内嵌状态
     */
    data?: (MaaFWEmbeddedStatusData | null);
};

