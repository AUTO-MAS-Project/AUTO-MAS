/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MysteryContextOut } from '../models/MysteryContextOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MysteryService {
    /**
     * 获取神秘入口申请信息
     * @returns MysteryContextOut Successful Response
     * @throws ApiError
     */
    public static getMysteryContextApiMysteryContextGet(): CancelablePromise<MysteryContextOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/mystery/context',
            errors: {
                503: `Service Unavailable`,
            },
        });
    }
}
