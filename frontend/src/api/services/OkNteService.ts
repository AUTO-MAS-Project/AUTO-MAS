/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OkNteService {
    /**
     * 获取 OK-NTE 配置文件列表及 schema
     * 获取 OK-NTE 配置文件列表及 schema 定义。
     * 读写 per-user 配置目录（data/{script_id}/Default/ConfigFile/），
     * 若为空则自动从 OK-NTE configs 目录初始化默认配置。
     *
     * Args:
     * script_id: OK-NTE 脚本 ID
     *
     * Returns:
     * dict: 包含配置文件列表和 schema 的响应
     * @param scriptId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getOkNteConfigsListApiScriptsOkNteConfigsListPost(
        scriptId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/oknte/configs/list',
            query: {
                'script_id': scriptId,
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
     * filename: 配置文件名（如 DailyTask.json）
     * data: 要更新的配置数据
     *
     * Returns:
     * dict: 操作结果
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static updateOkNteConfigApiScriptsOkNteConfigsUpdatePost(
        requestBody: any,
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
     * configs: { filename: data } 格式的配置数据
     *
     * Returns:
     * dict: 操作结果
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static batchUpdateOkNteConfigsApiScriptsOkNteConfigsBatchUpdatePost(
        requestBody: any,
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


