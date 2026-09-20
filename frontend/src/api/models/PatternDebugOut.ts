/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PatternDebugResultItem } from './PatternDebugResultItem';
/**
 * 日志模式调试响应
 */
export type PatternDebugOut = {
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
     * 配置级错误（正则/表达式语法错误等）
     */
    configError?: (string | null);
    /**
     * 是否为多行聚合模式
     */
    isMultiline?: boolean;
    /**
     * 逐行/逐窗口调试结果
     */
    results?: Array<PatternDebugResultItem>;
};

