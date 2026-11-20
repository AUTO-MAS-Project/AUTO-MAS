/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BannerSubscriptionsIn } from '../models/BannerSubscriptionsIn';
import type { BannerWatchOut } from '../models/BannerWatchOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class BannerWatchService {
    /**
     * Get Banner Watch
     * @returns BannerWatchOut Successful Response
     * @throws ApiError
     */
    public static getBannerWatch(): CancelablePromise<BannerWatchOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/banner-watch',
        });
    }
    /**
     * Put Banner Subscriptions
     * @param requestBody
     * @returns BannerWatchOut Successful Response
     * @throws ApiError
     */
    public static updateBannerSubscriptions(
        requestBody: BannerSubscriptionsIn,
    ): CancelablePromise<BannerWatchOut> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/banner-watch/subscriptions',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
