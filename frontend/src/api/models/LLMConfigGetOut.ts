/* LLM Config Get Out */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LLMProviderIndexItem } from './LLMProviderIndexItem';
import type { LLMProviderConfig } from './LLMProviderConfig';
import type { LLMGlobalSettings } from './LLMGlobalSettings';
export type LLMConfigGetOut = {
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
     * 提供商索引列表
     */
    index: Array<LLMProviderIndexItem>;
    /**
     * 提供商配置数据
     */
    data: Record<string, LLMProviderConfig>;
    /**
     * 全局设置
     */
    settings: LLMGlobalSettings;
    /**
     * 预设提供商配置
     */
    preset_providers: Record<string, Record<string, string>>;
};
