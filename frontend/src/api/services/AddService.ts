/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2InstanceCreateIn } from '../models/Emulator2InstanceCreateIn';
import type { Emulator2InstanceCreateOut } from '../models/Emulator2InstanceCreateOut';
import type { Emulator2PathAddIn } from '../models/Emulator2PathAddIn';
import type { Emulator2PathAddOut } from '../models/Emulator2PathAddOut';
import type { EmulatorCreateIn } from '../models/EmulatorCreateIn';
import type { EmulatorCreateOut } from '../models/EmulatorCreateOut';
import type { PlanCreateIn } from '../models/PlanCreateIn';
import type { PlanCreateOut } from '../models/PlanCreateOut';
import type { QueueCreateIn } from '../models/QueueCreateIn';
import type { QueueCreateOut } from '../models/QueueCreateOut';
import type { QueueItemCreateIn } from '../models/QueueItemCreateIn';
import type { QueueItemCreateOut } from '../models/QueueItemCreateOut';
import type { ScriptCreateIn } from '../models/ScriptCreateIn';
import type { ScriptCreateOut } from '../models/ScriptCreateOut';
import type { TimeSetCreateIn } from '../models/TimeSetCreateIn';
import type { TimeSetCreateOut } from '../models/TimeSetCreateOut';
import type { UserCreateIn } from '../models/UserCreateIn';
import type { UserCreateOut } from '../models/UserCreateOut';
import type { WebhookCreateIn } from '../models/WebhookCreateIn';
import type { WebhookCreateOut } from '../models/WebhookCreateOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AddService {
    /**
     * 添加脚本
     * @param requestBody
     * @returns ScriptCreateOut Successful Response
     * @throws ApiError
     */
    public static addScriptApiScriptsAddPost(
        requestBody: ScriptCreateIn,
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
        requestBody: UserCreateIn,
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
     * 添加webhook项
     * @param requestBody
     * @returns WebhookCreateOut Successful Response
     * @throws ApiError
     */
    public static addWebhookApiScriptsWebhookAddPost(
        requestBody: WebhookCreateIn,
    ): CancelablePromise<WebhookCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/webhook/add',
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
     * 添加模拟器项
     * @param requestBody
     * @returns EmulatorCreateOut Successful Response
     * @throws ApiError
     */
    public static addEmulatorApiEmulatorAddPost(
        requestBody?: (EmulatorCreateIn | null),
    ): CancelablePromise<EmulatorCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加模拟器路径
     * 探测版本 → 落库 → 为该安装的实例分配设备号。
     *
     * 版本不合要求时返回 ``ok=False`` 与原因枚举，而不是抛错。
     * @param requestBody
     * @returns Emulator2PathAddOut Successful Response
     * @throws ApiError
     */
    public static addPathApiEmulator2PathsAddPost(
        requestBody: Emulator2PathAddIn,
    ): CancelablePromise<Emulator2PathAddOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/paths/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 新建模拟器实例
     * 在某条模拟器安装下新建一个实例，并给它分配设备号。
     *
     * 新建成功与否**不看命令返回码**——雷电新建成功时返回码也不为 0，
     * 判据是列表里有没有多出实例。
     * @param requestBody
     * @returns Emulator2InstanceCreateOut Successful Response
     * @throws ApiError
     */
    public static createInstanceApiEmulator2InstancesCreatePost(
        requestBody: Emulator2InstanceCreateIn,
    ): CancelablePromise<Emulator2InstanceCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/instances/create',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加调度队列
     * @param requestBody
     * @returns QueueCreateOut Successful Response
     * @throws ApiError
     */
    public static addQueueApiQueueAddPost(
        requestBody?: (QueueCreateIn | null),
    ): CancelablePromise<QueueCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加定时项
     * @param requestBody
     * @returns TimeSetCreateOut Successful Response
     * @throws ApiError
     */
    public static addTimeSetApiQueueTimeAddPost(
        requestBody: TimeSetCreateIn,
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
        requestBody: QueueItemCreateIn,
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
     * 添加webhook项
     * @param requestBody
     * @returns WebhookCreateOut Successful Response
     * @throws ApiError
     */
    public static addWebhookApiSettingWebhookAddPost(
        requestBody?: (WebhookCreateIn | null),
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
}
