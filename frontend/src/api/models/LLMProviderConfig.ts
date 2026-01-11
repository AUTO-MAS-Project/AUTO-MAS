/* LLM Provider Config */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LLMProviderConfig_Info } from './LLMProviderConfig_Info';
import type { LLMProviderConfig_Data } from './LLMProviderConfig_Data';
export type LLMProviderConfig = {
    /**
     * 提供商基础信息
     */
    Info?: (LLMProviderConfig_Info | null);
    /**
     * 提供商配置数据
     */
    Data?: (LLMProviderConfig_Data | null);
};
