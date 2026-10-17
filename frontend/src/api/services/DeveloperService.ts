/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaBasePresetOut } from '../models/MaaBasePresetOut';
import type { MaaBasePresetUpdateIn } from '../models/MaaBasePresetUpdateIn';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DeveloperService {
    /**
     * 读取 MAA 内置预设（仅开发模式）
     * 读取当前进程正在使用的 MAA 内置预设。
     * @returns MaaBasePresetOut Successful Response
     * @throws ApiError
     */
    public static getMaaBasePresetApiApiDeveloperMaaBasePresetGet(): CancelablePromise<MaaBasePresetOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/developer/maa/base-preset',
        });
    }
    /**
     * 保存 MAA 内置预设（仅开发模式）
     * 校验并保存完整 MAA 内置预设，同时刷新当前进程内存。
     * @param requestBody
     * @returns MaaBasePresetOut Successful Response
     * @throws ApiError
     */
    public static updateMaaBasePresetApiApiDeveloperMaaBasePresetPost(
        requestBody: MaaBasePresetUpdateIn,
    ): CancelablePromise<MaaBasePresetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/developer/maa/base-preset',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
