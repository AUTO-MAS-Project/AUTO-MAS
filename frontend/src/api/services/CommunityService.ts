/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CommunityActivityOut } from '../models/CommunityActivityOut';
import type { CommunityActivityQueryIn } from '../models/CommunityActivityQueryIn';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class CommunityService {
    /**
     * 查询游戏社区日常活跃度
     * 查询游戏社区日常活动，不占用签到流程锁。
     * @param requestBody
     * @returns CommunityActivityOut Successful Response
     * @throws ApiError
     */
    public static queryCommunityActivityApiToolsCommunityActivityQueryPost(
        requestBody: CommunityActivityQueryIn,
    ): CancelablePromise<CommunityActivityOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/community/activity/query',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
