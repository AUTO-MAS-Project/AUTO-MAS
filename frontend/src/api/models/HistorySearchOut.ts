/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HistoryBucket } from './HistoryBucket';
export type HistorySearchOut = {
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
     * 日期 → 用户名 → 记录与统计
     */
    data: Record<string, Record<string, HistoryBucket>>;
};

