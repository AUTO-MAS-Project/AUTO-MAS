/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_batch_update_okww_configs_api_scripts_okww_configs_batch_update_post } from '../models/Body_batch_update_okww_configs_api_scripts_okww_configs_batch_update_post';
import type { Body_update_okww_config_api_scripts_okww_configs_update_post } from '../models/Body_update_okww_config_api_scripts_okww_configs_update_post';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OkwwService {
    /**
     * 获取 OK-WW 配置文件列表及 schema
     * 获取 OK-WW 配置文件列表及 schema 定义。
     * 读写 per-user 配置目录（data/{script_id}/Default/ConfigFile/），
     * 若为空则自动从 ok-ww configs 目录初始化默认配置。
     *
     * Args:
     * script_id: OK-WW 脚本 ID
     *
     * Returns:
     * dict: 包含配置文件列表和 schema 的响应
     * @param scriptId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getOkwwConfigsListApiScriptsOkwwConfigsListPost(
        scriptId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okww/configs/list',
            query: {
                'script_id': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新 OK-WW 配置文件
     * 更新 OK-WW 配置文件
     *
     * Args:
     * script_id: OK-WW 脚本 ID
     * filename: 配置文件名（如 DailyTask.json）
     * data: 要更新的配置数据
     *
     * Returns:
     * dict: 操作结果
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static updateOkwwConfigApiScriptsOkwwConfigsUpdatePost(
        requestBody: Body_update_okww_config_api_scripts_okww_configs_update_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okww/configs/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量更新 OK-WW 配置文件
     * 批量更新 OK-WW 配置文件
     *
     * Args:
     * script_id: OK-WW 脚本 ID
     * configs: { filename: data } 格式的配置数据
     *
     * Returns:
     * dict: 操作结果
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static batchUpdateOkwwConfigsApiScriptsOkwwConfigsBatchUpdatePost(
        requestBody: Body_batch_update_okww_configs_api_scripts_okww_configs_batch_update_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okww/configs/batch-update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
