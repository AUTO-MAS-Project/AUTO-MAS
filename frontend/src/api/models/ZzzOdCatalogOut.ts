/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdCatalogItemOut } from './ZzzOdCatalogItemOut';
export type ZzzOdCatalogOut = {
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
     * 任务目录
     */
    data: Array<ZzzOdCatalogItemOut>;
};

