/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SignFlowAccountCollectionOut } from './SignFlowAccountCollectionOut';
/**
 * 游戏社区账号组列表响应
 */
export type SignFlowAccountsListOut = {
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
     * 账号组列表
     */
    data?: SignFlowAccountCollectionOut;
};

