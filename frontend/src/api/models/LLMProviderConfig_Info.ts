/* LLM Provider Config Info */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LLMProviderConfig_Info = {
    /**
     * 提供商名称
     */
    Name?: (string | null);
    /**
     * 提供商类型
     */
    Type?: ('openai' | 'claude' | 'deepseek' | 'qwen' | 'mimo' | 'custom' | null);
    /**
     * 是否激活
     */
    Active?: (boolean | null);
};
