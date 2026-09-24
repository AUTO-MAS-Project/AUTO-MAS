/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWShellInstanceImportItem } from './MaaFWShellInstanceImportItem';
export type MaaFWShellInstanceImportOut = {
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
     * 逐个实例的导入结果，顺序同请求
     */
    data?: Array<MaaFWShellInstanceImportItem>;
};

