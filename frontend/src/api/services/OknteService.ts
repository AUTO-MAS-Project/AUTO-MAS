/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post } from '../models/Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OknteService {
    /**
     * 获取 OK-NTE 配置文件列表及 schema
     * 获取 OK-NTE 配置文件列表及 schema 定义。
     * 读写用户快速配置目录，首次从已有来源初始化，不修改来源文件。
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
