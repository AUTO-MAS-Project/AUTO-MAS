/* LLM Usage Statistics Out */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LLMUsageStatisticsOut = {
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
     * 总 Token 数
     */
    total_tokens?: number;
    /**
     * 总请求数
     */
    total_requests?: number;
    /**
     * 每次请求平均 Token 数
     */
    average_tokens_per_request?: number;
    /**
     * 总输入 Token 数
     */
    input_tokens?: number;
    /**
     * 总输出 Token 数
     */
    output_tokens?: number;
    /**
     * 当天统计
     */
    daily?: (Record<string, any> | null);
    /**
     * 本周统计
     */
    weekly?: (Record<string, any> | null);
    /**
     * 本月统计
     */
    monthly?: (Record<string, any> | null);
};
