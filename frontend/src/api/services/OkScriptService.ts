/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkScriptProbeIn } from '../models/OkScriptProbeIn';
import type { OkScriptProbeOut } from '../models/OkScriptProbeOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OkScriptService {
    /**
     * 识别 ok-script 项目
     * 识别安装目录里的 ok-script 项目，返回项目名、版本与一次性任务列表。
     * @param requestBody
     * @returns OkScriptProbeOut Successful Response
     * @throws ApiError
     */
    public static probeOkscriptProjectApiApiScriptsOkscriptProbePost(
        requestBody: OkScriptProbeIn,
    ): CancelablePromise<OkScriptProbeOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okscript/probe',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
