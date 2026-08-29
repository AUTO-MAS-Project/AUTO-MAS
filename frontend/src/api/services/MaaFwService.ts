/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWInterfacePreviewIn } from '../models/MaaFWInterfacePreviewIn';
import type { MaaFWInterfacePreviewOut } from '../models/MaaFWInterfacePreviewOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MaaFwService {
    /**
     * 预览 MaaFW interface
     * 读取 MaaFW 项目 interface，并返回 controller/resource/task 摘要。
     * @param requestBody
     * @returns MaaFWInterfacePreviewOut Successful Response
     * @throws ApiError
     */
    public static previewMaafwInterfaceApiScriptsMaafwPreviewPost(
        requestBody: MaaFWInterfacePreviewIn,
    ): CancelablePromise<MaaFWInterfacePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
