/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class BaahService {
    /**
     * 获取 BAAH 配置文件名列表
     * 返回 BAAH 配置目录下已有的配置文件名（不含 ``.json`` 后缀）。
     * @param scriptId
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getBaahConfigNamesApiApiScriptsBaahConfigNamesGet(
        scriptId: string,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/baah/config-names',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
