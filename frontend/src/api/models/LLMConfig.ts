/* LLM Config */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LLMGlobalSettings } from './LLMGlobalSettings';
import type { LLMProviderConfig } from './LLMProviderConfig';
export type LLMConfig = {
    /**
     * 全局设置
     */
    LLM?: (LLMGlobalSettings | null);
    /**
     * 提供商配置
     */
    Providers?: (Record<string, LLMProviderConfig> | null);
};
