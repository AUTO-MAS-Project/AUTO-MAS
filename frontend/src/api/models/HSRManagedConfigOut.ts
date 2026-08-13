/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRManagedConfigData } from './HSRManagedConfigData';
export type HSRManagedConfigOut = {
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
     * 托管配置
     */
    data?: (HSRManagedConfigData | null);
};

