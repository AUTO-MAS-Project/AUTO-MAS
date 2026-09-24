/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRCloudLoginData } from './HSRCloudLoginData';
export type HSRCloudLoginOut = {
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
     * 登录结果
     */
    data?: (HSRCloudLoginData | null);
};

