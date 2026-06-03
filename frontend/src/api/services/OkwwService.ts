/* istanbul ignore file */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';

export class OkwwService {
    /**
     * 获取 OK-WW 配置文件列表及 schema
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
     */
    public static updateOkwwConfigApiScriptsOkwwConfigsUpdatePost(
        scriptId: string,
        filename: string,
        data: Record<string, any>,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okww/configs/update',
            body: {
                'script_id': scriptId,
                'filename': filename,
                'data': data,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }

    /**
     * 批量更新 OK-WW 配置文件
     */
    public static batchUpdateOkwwConfigsApiScriptsOkwwConfigsBatchUpdatePost(
        scriptId: string,
        configs: Record<string, Record<string, any>>,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okww/configs/batch-update',
            body: {
                'script_id': scriptId,
                'configs': configs,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
