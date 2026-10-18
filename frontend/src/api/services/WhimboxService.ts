/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WhimboxTaskCatalogOut } from '../models/WhimboxTaskCatalogOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class WhimboxService {
    /**
     * 获取奇想盒一条龙任务目录
     * 下发一条龙任务目录（步骤开关 + 目标/参数字段）。
     *
     * 字段定义与值域从上游安装目录三件套（default_config / setting_options /
     * material）运行时机械转换，MAS 发版不管理；上游升级后下次读取自动生效。
     * @param scriptId
     * @returns WhimboxTaskCatalogOut Successful Response
     * @throws ApiError
     */
    public static getWhimboxTaskCatalogApiApiScriptsWhimboxTaskCatalogGet(
        scriptId?: (string | null),
    ): CancelablePromise<WhimboxTaskCatalogOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/whimbox/task-catalog',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
