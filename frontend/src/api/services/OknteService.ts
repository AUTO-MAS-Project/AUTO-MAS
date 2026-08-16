/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post } from '../models/Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post';
import type { Body_update_oknte_config_api_scripts_oknte_configs_update_post } from '../models/Body_update_oknte_config_api_scripts_oknte_configs_update_post';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OknteService {
    /**
     * 获取 OK-NTE 配置文件列表及 schema
     * 获取 OK-NTE 配置文件列表及 schema 定义。
     * 读写用户配置目录（data/{script_id}/{user_id}/ConfigFile/），
     * 若为空则自动从 ok-nte configs 目录初始化默认配置。
     *
     * Args:
     * script_id: OK-NTE 脚本 ID
     * user_id: 用户 ID
     *
     * Returns:
     * dict: 包含配置文件列表和 schema 的响应
     * @param scriptId
     * @param userId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getOknteConfigsListApiScriptsOknteConfigsListPost(
        scriptId: string,
        userId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/oknte/configs/list',
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
     * 更新 OK-NTE 配置文件
     * 更新 OK-NTE 配置文件
     *
     * Args:
     * script_id: OK-NTE 脚本 ID
     * user_id: 用户 ID
     * filename: 配置文件名（如 DailyTask.json）
     * data: 要更新的配置数据
     *
     * Returns:
     * dict: 操作结果
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static updateOknteConfigApiScriptsOknteConfigsUpdatePost(
        requestBody: Body_update_oknte_config_api_scripts_oknte_configs_update_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/oknte/configs/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量更新 OK-NTE 配置文件
     * 批量更新 OK-NTE 配置文件
     *
     * Args:
     * script_id: OK-NTE 脚本 ID
     * user_id: 用户 ID
     * configs: { filename: data } 格式的配置数据
     *
     * Returns:
     * dict: 操作结果
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static batchUpdateOknteConfigsApiScriptsOknteConfigsBatchUpdatePost(
        requestBody: Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/oknte/configs/batch-update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
