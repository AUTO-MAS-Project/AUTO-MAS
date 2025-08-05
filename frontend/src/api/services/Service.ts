/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InfoOut } from '../models/InfoOut.ts';
import type { OutBase } from '../models/OutBase.ts';
import type { PlanCreateIn } from '../models/PlanCreateIn.ts';
import type { PlanCreateOut } from '../models/PlanCreateOut.ts';
import type { PlanDeleteIn } from '../models/PlanDeleteIn.ts';
import type { PlanGetIn } from '../models/PlanGetIn.ts';
import type { PlanGetOut } from '../models/PlanGetOut.ts';
import type { PlanReorderIn } from '../models/PlanReorderIn.ts';
import type { PlanUpdateIn } from '../models/PlanUpdateIn.ts';
import type { QueueCreateOut } from '../models/QueueCreateOut.ts';
import type { QueueDeleteIn } from '../models/QueueDeleteIn.ts';
import type { QueueGetIn } from '../models/QueueGetIn.ts';
import type { QueueGetOut } from '../models/QueueGetOut.ts';
import type { QueueItemCreateOut } from '../models/QueueItemCreateOut.ts';
import type { QueueItemDeleteIn } from '../models/QueueItemDeleteIn.ts';
import type { QueueItemReorderIn } from '../models/QueueItemReorderIn.ts';
import type { QueueItemUpdateIn } from '../models/QueueItemUpdateIn.ts';
import type { QueueReorderIn } from '../models/QueueReorderIn.ts';
import type { QueueSetInBase } from '../models/QueueSetInBase.ts';
import type { QueueUpdateIn } from '../models/QueueUpdateIn.ts';
import type { ScriptCreateIn } from '../models/ScriptCreateIn.ts';
import type { ScriptCreateOut } from '../models/ScriptCreateOut.ts';
import type { ScriptDeleteIn } from '../models/ScriptDeleteIn.ts';
import type { ScriptGetIn } from '../models/ScriptGetIn.ts';
import type { ScriptGetOut } from '../models/ScriptGetOut.ts';
import type { ScriptReorderIn } from '../models/ScriptReorderIn.ts';
import type { ScriptUpdateIn } from '../models/ScriptUpdateIn.ts';
import type { SettingGetOut } from '../models/SettingGetOut.ts';
import type { SettingUpdateIn } from '../models/SettingUpdateIn.ts';
import type { TimeSetCreateOut } from '../models/TimeSetCreateOut.ts';
import type { TimeSetDeleteIn } from '../models/TimeSetDeleteIn.ts';
import type { TimeSetReorderIn } from '../models/TimeSetReorderIn.ts';
import type { TimeSetUpdateIn } from '../models/TimeSetUpdateIn.ts';
import type { UserCreateOut } from '../models/UserCreateOut.ts';
import type { UserDeleteIn } from '../models/UserDeleteIn.ts';
import type { UserInBase } from '../models/UserInBase.ts';
import type { UserReorderIn } from '../models/UserReorderIn.ts';
import type { UserUpdateIn } from '../models/UserUpdateIn.ts';
import type { CancelablePromise } from '../core/CancelablePromise.ts';
import { OpenAPI } from '../core/OpenAPI.ts';
import { request as __request } from '../core/request.ts';
export class Service {
    /**
     * 获取关卡号信息
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static getStageInfoApiInfoStagePost(): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/stage',
        });
    }
    /**
     * 获取通知信息
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static getNoticeInfoApiInfoNoticePost(): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/notice',
        });
    }
    /**
     * 获取可下载应用信息
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static getAppsInfoApiInfoAppsInfoPost(): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/apps_info',
        });
    }
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
     * 查询脚本配置信息
     * @param requestBody
     * @returns ScriptGetOut Successful Response
     * @throws ApiError
     */
    public static getScriptsApiScriptsGetPost(
        requestBody: ScriptGetIn,
    ): CancelablePromise<ScriptGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
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
     * 添加用户
     * @param requestBody
     * @returns UserCreateOut Successful Response
     * @throws ApiError
     */
    public static addUserApiScriptsUserAddPost(
        requestBody: UserInBase,
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
     * 查询计划表配置信息
     * @param requestBody
     * @returns PlanGetOut Successful Response
     * @throws ApiError
     */
    public static getPlanApiPlanGetPost(
        requestBody: PlanGetIn,
    ): CancelablePromise<PlanGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plan/get',
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
     * 查询调度队列配置信息
     * @param requestBody
     * @returns QueueGetOut Successful Response
     * @throws ApiError
     */
    public static getQueuesApiQueueGetPost(
        requestBody: QueueGetIn,
    ): CancelablePromise<QueueGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/get',
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
     * 重新排序时间设置
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
     * 查询配置
     * 查询配置
     * @returns SettingGetOut Successful Response
     * @throws ApiError
     */
    public static getScriptsApiSettingGetPost(): CancelablePromise<SettingGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/get',
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
}
