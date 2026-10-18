/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdRecycleEntryOut } from './ZzzOdRecycleEntryOut';
export type ZzzOdRecycleOut = {
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
     * 回收池条目
     */
    data: Array<ZzzOdRecycleEntryOut>;
};

