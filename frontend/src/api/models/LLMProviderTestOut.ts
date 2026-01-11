/* LLM Provider Test Out */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LLMProviderTestOut = {
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
     * 测试是否成功
     */
    success: boolean;
    /**
     * 响应时间（秒）
     */
    response_time?: number;
    /**
     * 测试使用的模型
     */
    model?: string;
};
