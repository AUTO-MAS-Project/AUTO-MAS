/* LLM Provider Update In */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LLMProviderConfig } from './LLMProviderConfig';
export type LLMProviderUpdateIn = {
    /**
     * 提供商 ID
     */
    providerId: string;
    /**
     * 提供商更新数据
     */
    data: LLMProviderConfig;
};
