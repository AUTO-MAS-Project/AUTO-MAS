/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRStageOptionsOut } from '../models/HSRStageOptionsOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class HsrService {
    /**
     * 获取 HSR 体力副本动态选项
     * 按体力执行脚本返回 M7A / SRA 原生副本字段。
     * @param scriptId
     * @param engine
     * @returns HSRStageOptionsOut Successful Response
     * @throws ApiError
     */
    public static getHsrStageOptionsApiApiScriptsHsrStageOptionsGet(
        scriptId?: (string | null),
        engine: 'M7A' | 'SRA' = 'M7A',
    ): CancelablePromise<HSRStageOptionsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/stage-options',
            query: {
                'scriptId': scriptId,
                'engine': engine,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
