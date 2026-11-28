/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SignFlowAccountGroupConfig } from './SignFlowAccountGroupConfig';
/**
 * 游戏社区账号组创建响应
 */
export type SignFlowAccountCreateOut = {
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
     * 账号组 UUID
     */
    accountId?: string;
    /**
     * 账号组配置
     */
    data?: SignFlowAccountGroupConfig;
};

