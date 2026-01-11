/* LLM Usage History Out */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TokenUsageRecord } from './TokenUsageRecord';
export type LLMUsageHistoryOut = {
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
     * 使用记录列表
     */
    records: Array<TokenUsageRecord>;
    /**
     * 总记录数
     */
    total_count?: number;
};
