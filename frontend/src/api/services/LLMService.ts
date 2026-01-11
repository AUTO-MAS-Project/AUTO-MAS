/* LLM Service */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LLMConfigGetOut } from '../models/LLMConfigGetOut';
import type { LLMConfigUpdateIn } from '../models/LLMConfigUpdateIn';
import type { LLMProviderCreateIn } from '../models/LLMProviderCreateIn';
import type { LLMProviderCreateOut } from '../models/LLMProviderCreateOut';
import type { LLMProviderDeleteIn } from '../models/LLMProviderDeleteIn';
import type { LLMProviderTestIn } from '../models/LLMProviderTestIn';
import type { LLMProviderTestOut } from '../models/LLMProviderTestOut';
import type { LLMProviderUpdateIn } from '../models/LLMProviderUpdateIn';
import type { LLMUsageHistoryOut } from '../models/LLMUsageHistoryOut';
import type { LLMUsageQueryIn } from '../models/LLMUsageQueryIn';
import type { LLMUsageStatisticsOut } from '../models/LLMUsageStatisticsOut';
import type { OutBase } from '../models/OutBase';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';

export class LLMService {
    /**
     * 获取 LLM 配置
     * @returns LLMConfigGetOut Successful Response
     * @throws ApiError
     */
    public static getLLMConfigApiLlmConfigGetPost(): CancelablePromise<LLMConfigGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/llm/config/get',
        });
    }

    /**
     * 更新 LLM 全局配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateLLMConfigApiLlmConfigUpdatePost(
        requestBody: LLMConfigUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/llm/config/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }

    /**
     * 添加 LLM 提供商
     * @param requestBody
     * @returns LLMProviderCreateOut Successful Response
     * @throws ApiError
     */
    public static addLLMProviderApiLlmProviderAddPost(
        requestBody?: LLMProviderCreateIn,
    ): CancelablePromise<LLMProviderCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/llm/provider/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }

    /**
     * 更新 LLM 提供商配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateLLMProviderApiLlmProviderUpdatePost(
        requestBody: LLMProviderUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/llm/provider/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }

    /**
     * 删除 LLM 提供商
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteLLMProviderApiLlmProviderDeletePost(
        requestBody: LLMProviderDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/llm/provider/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }

    /**
     * 测试 LLM 提供商连接
     * @param requestBody
     * @returns LLMProviderTestOut Successful Response
     * @throws ApiError
     */
    public static testLLMProviderApiLlmProviderTestPost(
        requestBody: LLMProviderTestIn,
    ): CancelablePromise<LLMProviderTestOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/llm/provider/test',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }

    /**
     * 获取 Token 使用统计
     * @param requestBody
     * @returns LLMUsageStatisticsOut Successful Response
     * @throws ApiError
     */
    public static getLLMUsageStatisticsApiLlmUsageStatisticsPost(
        requestBody?: LLMUsageQueryIn,
    ): CancelablePromise<LLMUsageStatisticsOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/llm/usage/statistics',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }

    /**
     * 获取 Token 使用历史
     * @param requestBody
     * @returns LLMUsageHistoryOut Successful Response
     * @throws ApiError
     */
    public static getLLMUsageHistoryApiLlmUsageHistoryPost(
        requestBody?: LLMUsageQueryIn,
    ): CancelablePromise<LLMUsageHistoryOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/llm/usage/history',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
