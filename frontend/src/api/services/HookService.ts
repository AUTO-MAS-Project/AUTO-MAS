/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HookMetaIn } from '../models/HookMetaIn';
import type { HookMetaOut } from '../models/HookMetaOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class HookService {
    /**
     * 读取 Hook 元数据（静态解析）
     * @param requestBody
     * @returns HookMetaOut Successful Response
     * @throws ApiError
     */
    public static getHookMetaApiHooksMetaPost(
        requestBody: HookMetaIn,
    ): CancelablePromise<HookMetaOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/hooks/meta',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
