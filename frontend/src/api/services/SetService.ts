/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameCalendarActivityUpdateIn } from '../models/GameCalendarActivityUpdateIn';
import type { OutBase } from '../models/OutBase';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SetService {
    /**
     * 设置终末地活动完成状态
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setEndfieldActivityCompletionApiInfoEndfieldActivityCompletionsPost(
        requestBody: GameCalendarActivityUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/endfield/activity/completions',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
