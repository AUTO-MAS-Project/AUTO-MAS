/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2InstanceDeleteIn } from '../models/Emulator2InstanceDeleteIn';
import type { Emulator2InstanceDeleteOut } from '../models/Emulator2InstanceDeleteOut';
import type { Emulator2PathRemoveIn } from '../models/Emulator2PathRemoveIn';
import type { Emulator2PathRemoveOut } from '../models/Emulator2PathRemoveOut';
import type { EmulatorDeleteIn } from '../models/EmulatorDeleteIn';
import type { OutBase } from '../models/OutBase';
import type { PlanDeleteIn } from '../models/PlanDeleteIn';
import type { QueueDeleteIn } from '../models/QueueDeleteIn';
import type { QueueItemDeleteIn } from '../models/QueueItemDeleteIn';
import type { ScriptDeleteIn } from '../models/ScriptDeleteIn';
import type { TimeSetDeleteIn } from '../models/TimeSetDeleteIn';
import type { UserDeleteIn } from '../models/UserDeleteIn';
import type { WebhookDeleteIn } from '../models/WebhookDeleteIn';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DeleteService {
    /**
     * 删除脚本
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteScriptApiScriptsDeletePost(
        requestBody: ScriptDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除用户
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteUserApiScriptsUserDeletePost(
        requestBody: UserDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除webhook项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteWebhookApiScriptsWebhookDeletePost(
        requestBody: WebhookDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/webhook/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除计划表
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deletePlanApiPlanDeletePost(
        requestBody: PlanDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plan/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除模拟器项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteEmulatorApiEmulatorDeletePost(
        requestBody: EmulatorDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 移除模拟器路径
     * 移除一条路径。设备号**失效并保留**，不会再分配给其他设备。
     * @param requestBody
     * @returns Emulator2PathRemoveOut Successful Response
     * @throws ApiError
     */
    public static removePathApiEmulator2PathsRemovePost(
        requestBody: Emulator2PathRemoveIn,
    ): CancelablePromise<Emulator2PathRemoveOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/paths/remove',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除模拟器实例
     * 删除一个实例。实例必须先关闭。
     *
     * 设备号不写墓碑——以后在同一原生索引重建实例仍然是这个设备号；
     * 在那之前该设备号显示为「未找到」，绑定它的脚本下一次执行直接失败。
     * @param requestBody
     * @returns Emulator2InstanceDeleteOut Successful Response
     * @throws ApiError
     */
    public static deleteInstanceApiEmulator2InstancesDeletePost(
        requestBody: Emulator2InstanceDeleteIn,
    ): CancelablePromise<Emulator2InstanceDeleteOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/instances/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除调度队列
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteQueueApiQueueDeletePost(
        requestBody: QueueDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除定时项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteTimeSetApiQueueTimeDeletePost(
        requestBody: TimeSetDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/time/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除队列项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteItemApiQueueItemDeletePost(
        requestBody: QueueItemDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/item/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除webhook项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteWebhookApiSettingWebhookDeletePost(
        requestBody: WebhookDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
