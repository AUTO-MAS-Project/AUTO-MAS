/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_batch_update_ok_script_configs_api_scripts_ok_script_configs_batch_update_post } from '../models/Body_batch_update_ok_script_configs_api_scripts_ok_script_configs_batch_update_post';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OkScriptService {
    /**
     * 获取 ok-script 配置文件列表和 schema
     * 根据当前 provider 获取隔离的用户配置文件和 schema。
     * @param scriptId
     * @param userId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getOkScriptConfigsListApiScriptsOkScriptConfigsListPost(
        scriptId: string,
        userId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/ok-script/configs/list',
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
     * 批量更新 ok-script 配置文件
     * 批量更新当前 provider 对应的用户配置 JSON。
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static batchUpdateOkScriptConfigsApiScriptsOkScriptConfigsBatchUpdatePost(
        requestBody: Body_batch_update_ok_script_configs_api_scripts_ok_script_configs_batch_update_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/ok-script/configs/batch-update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
