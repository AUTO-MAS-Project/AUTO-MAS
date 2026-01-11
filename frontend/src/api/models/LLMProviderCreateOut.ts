/* LLM Provider Create Out */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LLMProviderConfig } from './LLMProviderConfig';
export type LLMProviderCreateOut = {
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
     * 新创建的提供商 ID
     */
    providerId: string;
    /**
     * 提供商配置数据
     */
    data: LLMProviderConfig;
};
