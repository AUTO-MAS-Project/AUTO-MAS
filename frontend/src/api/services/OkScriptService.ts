/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_batch_update_ok_script_configs_api_scripts_ok_script_configs_batch_update_post } from '../models/Body_batch_update_ok_script_configs_api_scripts_ok_script_configs_batch_update_post';
import type { Body_inspect_ok_script_project_api_scripts_ok_script_inspect_post } from '../models/Body_inspect_ok_script_project_api_scripts_ok_script_inspect_post';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OkScriptService {
    /**
     * 解析 ok-script 项目 Manifest
     * 只读返回项目 Manifest，不导入或启动外部项目代码。
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static inspectOkScriptProjectApiScriptsOkScriptInspectPost(
        requestBody: Body_inspect_ok_script_project_api_scripts_ok_script_inspect_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/ok-script/inspect',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 ok-script 配置文件列表和 schema
     * 获取隔离用户配置；专项优先 schema，未知项目回退通用 JSON。
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
