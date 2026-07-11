/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_batch_update_okef_configs_api_scripts_okef_configs_batch_update_post } from '../models/Body_batch_update_okef_configs_api_scripts_okef_configs_batch_update_post';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OkefService {
    /**
     * 获取 OK-EF 配置文件列表和 schema
     * 获取 OK-EF 配置文件列表和 schema 定义。
     * 读取用户配置目录（data/{script_id}/{user_id}/ConfigFile/），
     * 若为空则自动从 OK-EF working/configs 目录初始化默认配置。
     * @param scriptId
     * @param userId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getOkefConfigsListApiScriptsOkefConfigsListPost(
        scriptId: string,
        userId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okef/configs/list',
            query: {
                'script_id': scriptId,
                'user_id': userId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量更新 OK-EF 配置文件
     * 批量更新 OK-EF 用户配置 JSON。
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static batchUpdateOkefConfigsApiScriptsOkefConfigsBatchUpdatePost(
        requestBody: Body_batch_update_okef_configs_api_scripts_okef_configs_batch_update_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okef/configs/batch-update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
