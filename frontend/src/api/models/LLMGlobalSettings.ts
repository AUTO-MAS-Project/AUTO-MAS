/* LLM Global Settings */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LLMGlobalSettings = {
    /**
     * 是否启用 LLM 功能
     */
    Enabled?: (boolean | null);
    /**
     * 当前激活的提供商 ID
     */
    ActiveProviderId?: (string | null);
    /**
     * API 调用超时时间（秒）
     */
    Timeout?: (number | null);
    /**
     * 最大重试次数
     */
    MaxRetries?: (number | null);
    /**
     * 速率限制（每分钟最大请求数）
     */
    RateLimit?: (number | null);
};
