/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmulatorReorderIn } from '../models/EmulatorReorderIn';
import type { EmulatorUpdateIn } from '../models/EmulatorUpdateIn';
import type { OutBase } from '../models/OutBase';
import type { PlanReorderIn } from '../models/PlanReorderIn';
import type { PlanUpdateIn } from '../models/PlanUpdateIn';
import type { QueueItemReorderIn } from '../models/QueueItemReorderIn';
import type { QueueItemUpdateIn } from '../models/QueueItemUpdateIn';
import type { QueueReorderIn } from '../models/QueueReorderIn';
import type { QueueUpdateIn } from '../models/QueueUpdateIn';
import type { ScriptFileIn } from '../models/ScriptFileIn';
import type { ScriptReorderIn } from '../models/ScriptReorderIn';
import type { ScriptUpdateIn } from '../models/ScriptUpdateIn';
import type { ScriptUrlIn } from '../models/ScriptUrlIn';
import type { SettingUpdateIn } from '../models/SettingUpdateIn';
import type { TimeSetReorderIn } from '../models/TimeSetReorderIn';
import type { TimeSetUpdateIn } from '../models/TimeSetUpdateIn';
import type { UserReorderIn } from '../models/UserReorderIn';
import type { UserSetIn } from '../models/UserSetIn';
import type { UserUpdateIn } from '../models/UserUpdateIn';
import type { WebhookReorderIn } from '../models/WebhookReorderIn';
import type { WebhookUpdateIn } from '../models/WebhookUpdateIn';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class UpdateService {
    /**
     * 更新脚本配置信息
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateScriptApiScriptsUpdatePost(
        requestBody: ScriptUpdateIn,
    ): CancelablePromise<OutBase> {
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
     * 重新排序脚本
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderScriptApiScriptsOrderPost(
        requestBody: ScriptReorderIn,
    ): CancelablePromise<OutBase> {
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
     * 从文件加载脚本配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static importScriptFromFileApiScriptsImportFilePost(
        requestBody: ScriptFileIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/import/file',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 从网络加载脚本配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static importScriptFromWebApiScriptsImportWebPost(
        requestBody: ScriptUrlIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/import/web',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新用户配置信息
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateUserApiScriptsUserUpdatePost(
        requestBody: UserUpdateIn,
    ): CancelablePromise<OutBase> {
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
     * 重新排序用户
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderUserApiScriptsUserOrderPost(
        requestBody: UserReorderIn,
    ): CancelablePromise<OutBase> {
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
     * 导入基建配置文件
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static importInfrastructureApiScriptsUserInfrastructurePost(
        requestBody: UserSetIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/infrastructure',
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateWebhookApiScriptsWebhookUpdatePost(
        requestBody: WebhookUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/webhook/update',
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderWebhookApiScriptsWebhookOrderPost(
        requestBody: WebhookReorderIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/webhook/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新计划表配置信息
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updatePlanApiPlanUpdatePost(
        requestBody: PlanUpdateIn,
    ): CancelablePromise<OutBase> {
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
     * 重新排序计划表
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderPlanApiPlanOrderPost(
        requestBody: PlanReorderIn,
    ): CancelablePromise<OutBase> {
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
     * 更新模拟器项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateEmulatorApiEmulatorUpdatePost(
        requestBody: EmulatorUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 重新排序模拟器项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderEmulatorApiEmulatorOrderPost(
        requestBody: EmulatorReorderIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/order',
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateQueueApiQueueUpdatePost(
        requestBody: QueueUpdateIn,
    ): CancelablePromise<OutBase> {
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderQueueApiQueueOrderPost(
        requestBody: QueueReorderIn,
    ): CancelablePromise<OutBase> {
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateTimeSetApiQueueTimeUpdatePost(
        requestBody: TimeSetUpdateIn,
    ): CancelablePromise<OutBase> {
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderTimeSetApiQueueTimeOrderPost(
        requestBody: TimeSetReorderIn,
    ): CancelablePromise<OutBase> {
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateItemApiQueueItemUpdatePost(
        requestBody: QueueItemUpdateIn,
    ): CancelablePromise<OutBase> {
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderItemApiQueueItemOrderPost(
        requestBody: QueueItemReorderIn,
    ): CancelablePromise<OutBase> {
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
     * 更新配置
     * 更新配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateScriptApiSettingUpdatePost(
        requestBody: SettingUpdateIn,
    ): CancelablePromise<OutBase> {
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateWebhookApiSettingWebhookUpdatePost(
        requestBody: WebhookUpdateIn,
    ): CancelablePromise<OutBase> {
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
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderWebhookApiSettingWebhookOrderPost(
        requestBody: WebhookReorderIn,
    ): CancelablePromise<OutBase> {
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
}
