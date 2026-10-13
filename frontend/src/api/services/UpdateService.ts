/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__api__OutBase } from '../models/app__api__OutBase';
import type { app__models__schema__OutBase } from '../models/app__models__schema__OutBase';
import type { GameReorderIn } from '../models/GameReorderIn';
import type { GameUpdateIn } from '../models/GameUpdateIn';
import type { InstanceUpdateIn } from '../models/InstanceUpdateIn';
import type { PlanReorderIn } from '../models/PlanReorderIn';
import type { PlanUpdateIn } from '../models/PlanUpdateIn';
import type { PluginCatalogUpdateIn } from '../models/PluginCatalogUpdateIn';
import type { PluginConfigUpdateIn } from '../models/PluginConfigUpdateIn';
import type { PluginRegistryUpdateIn } from '../models/PluginRegistryUpdateIn';
import type { QueueItemReorderIn } from '../models/QueueItemReorderIn';
import type { QueueItemUpdateIn } from '../models/QueueItemUpdateIn';
import type { QueueReorderIn } from '../models/QueueReorderIn';
import type { QueueUpdateIn } from '../models/QueueUpdateIn';
import type { ScriptReorderIn } from '../models/ScriptReorderIn';
import type { ScriptUpdateIn } from '../models/ScriptUpdateIn';
import type { SettingUpdateIn } from '../models/SettingUpdateIn';
import type { TimeSetReorderIn } from '../models/TimeSetReorderIn';
import type { TimeSetUpdateIn } from '../models/TimeSetUpdateIn';
import type { ToolsUpdateIn } from '../models/ToolsUpdateIn';
import type { UserReorderIn } from '../models/UserReorderIn';
import type { UserUpdateIn } from '../models/UserUpdateIn';
import type { WebhookReorderIn } from '../models/WebhookReorderIn';
import type { WebhookUpdateIn } from '../models/WebhookUpdateIn';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class UpdateService {
    /**
     * 更新工具配置
     * 更新工具配置（仅 Group 字段；账号组走独立端点）。
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateToolsApiToolsUpdatePost(
        requestBody: ToolsUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新配置
     * 更新全局设置（仅 Group 字段；``custom_webhooks`` 走独立端点）。
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateSettingApiSettingUpdatePost(
        requestBody: SettingUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新webhook项
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateWebhookApiSettingWebhookUpdatePost(
        requestBody: WebhookUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 重新排序webhook项
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static reorderWebhookApiSettingWebhookOrderPost(
        requestBody: WebhookReorderIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新调度队列配置信息
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateQueueApiQueueUpdatePost(
        requestBody: QueueUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 重新排序
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static reorderQueueApiQueueOrderPost(
        requestBody: QueueReorderIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新定时项
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateTimeSetApiQueueTimeUpdatePost(
        requestBody: TimeSetUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/time/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 重新排序定时项
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static reorderTimeSetApiQueueTimeOrderPost(
        requestBody: TimeSetReorderIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/time/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新队列项
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateItemApiQueueItemUpdatePost(
        requestBody: QueueItemUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/item/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 重新排序队列项
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static reorderItemApiQueueItemOrderPost(
        requestBody: QueueItemReorderIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/item/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新计划表
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updatePlanApiPlanUpdatePost(
        requestBody: PlanUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plan/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 计划表排序
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static orderPlansApiPlanOrderPost(
        requestBody: PlanReorderIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plan/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新脚本
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateScriptApiScriptsUpdatePost(
        requestBody: ScriptUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 脚本排序
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static orderScriptsApiScriptsOrderPost(
        requestBody: ScriptReorderIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新用户
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateUserApiScriptsUserUpdatePost(
        requestBody: UserUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 用户排序
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static orderUsersApiScriptsUserOrderPost(
        requestBody: UserReorderIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新游戏
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateGameApiGamesUpdatePost(
        requestBody: GameUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 游戏排序
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static orderGamesApiGamesOrderPost(
        requestBody: GameReorderIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新游戏设备
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateInstanceApiGamesInstancesUpdatePost(
        requestBody: InstanceUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/instances/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改插件注册表项（仅 enable/disable/reload/uninstall Trigger）
     * @param requestBody
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static updatePluginRegistryApiPluginRegistryUpdatePost(
        requestBody: PluginRegistryUpdateIn,
    ): CancelablePromise<app__models__schema__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_registry/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改目录项（透传全部字段）
     * @param requestBody
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static updatePluginCatalogApiPluginCatalogUpdatePost(
        requestBody: PluginCatalogUpdateIn,
    ): CancelablePromise<app__models__schema__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_catalog/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改插件自有配置（与注册表同一 uid）
     * @param requestBody
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static updatePluginConfigApiPluginConfigUpdatePost(
        requestBody: PluginConfigUpdateIn,
    ): CancelablePromise<app__models__schema__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_config/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
