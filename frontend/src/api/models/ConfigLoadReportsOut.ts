/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConfigLoadReportOut } from './ConfigLoadReportOut';
/**
 * 全部配置文件的加载状态（只读）
 */
export type ConfigLoadReportsOut = {
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
     * 按配置文件汇总的加载状态
     */
    data: Array<ConfigLoadReportOut>;
};
