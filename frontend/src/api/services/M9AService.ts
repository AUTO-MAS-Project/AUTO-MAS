/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class M9AService {
    /**
     * 获取 M9A 可用任务列表（排除 standalone 任务）
     * 获取 M9A 可用任务列表（排除 standalone 任务）
     *
     * 前端调用此接口获取可选择的任务列表，
     * 用于展示在用户编辑界面的任务选择区域。
     *
     * Args:
     * script_id: M9A 脚本 ID
     *
     * Returns:
     * dict: 包含任务列表的响应
     * @param scriptId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getM9AAvailableTasksApiScriptsM9ATasksAvailablePost(
        scriptId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/m9a/tasks/available',
            query: {
                'script_id': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
