/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameCreateIn } from '../models/GameCreateIn';
import type { GameCreateOut } from '../models/GameCreateOut';
import type { PlanCreateIn } from '../models/PlanCreateIn';
import type { PlanCreateOut } from '../models/PlanCreateOut';
import type { QueueCreateOut } from '../models/QueueCreateOut';
import type { QueueItemCreateOut } from '../models/QueueItemCreateOut';
import type { QueueSetInBase } from '../models/QueueSetInBase';
import type { ScriptCreateIn } from '../models/ScriptCreateIn';
import type { ScriptCreateOut } from '../models/ScriptCreateOut';
import type { SearchAddIn } from '../models/SearchAddIn';
import type { TimeSetCreateOut } from '../models/TimeSetCreateOut';
import type { UserCreateOut } from '../models/UserCreateOut';
import type { UserGetIn } from '../models/UserGetIn';
import type { WebhookCreateOut } from '../models/WebhookCreateOut';
import type { WebhookInBase } from '../models/WebhookInBase';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AddService {
    /**
     * 添加webhook项
     * @param requestBody
     * @returns WebhookCreateOut Successful Response
     * @throws ApiError
     */
    public static addWebhookApiSettingWebhookAddPost(
        requestBody?: (WebhookInBase | null),
    ): CancelablePromise<WebhookCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加调度队列
     * @returns QueueCreateOut Successful Response
     * @throws ApiError
     */
    public static addQueueApiQueueAddPost(): CancelablePromise<QueueCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/add',
        });
    }
    /**
     * 添加定时项
     * @param requestBody
     * @returns TimeSetCreateOut Successful Response
     * @throws ApiError
     */
    public static addTimeSetApiQueueTimeAddPost(
        requestBody: QueueSetInBase,
    ): CancelablePromise<TimeSetCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/time/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加队列项
     * @param requestBody
     * @returns QueueItemCreateOut Successful Response
     * @throws ApiError
     */
    public static addItemApiQueueItemAddPost(
        requestBody: QueueSetInBase,
    ): CancelablePromise<QueueItemCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/item/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加计划表
     * @param requestBody
     * @returns PlanCreateOut Successful Response
     * @throws ApiError
     */
    public static addPlanApiPlanAddPost(
        requestBody: PlanCreateIn,
    ): CancelablePromise<PlanCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plan/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加脚本
     * @param requestBody
     * @returns ScriptCreateOut Successful Response
     * @throws ApiError
     */
    public static addScriptApiScriptsAddPost(
        requestBody?: ScriptCreateIn,
    ): CancelablePromise<ScriptCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加用户
     * @param requestBody
     * @returns UserCreateOut Successful Response
     * @throws ApiError
     */
    public static addUserApiScriptsUserAddPost(
        requestBody: UserGetIn,
    ): CancelablePromise<UserCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加游戏
     * @param requestBody
     * @returns GameCreateOut Successful Response
     * @throws ApiError
     */
    public static addGameApiGamesAddPost(
        requestBody?: GameCreateIn,
    ): CancelablePromise<GameCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 将搜索结果写入游戏配置
     * @param requestBody
     * @returns GameCreateOut Successful Response
     * @throws ApiError
     */
    public static addSearchedGameApiGamesSearchAddPost(
        requestBody: SearchAddIn,
    ): CancelablePromise<GameCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/search/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
