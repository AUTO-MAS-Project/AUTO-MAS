/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { DispatchIn } from '../models/DispatchIn';
import type { GetStageIn } from '../models/GetStageIn';
import type { HistoryDataGetIn } from '../models/HistoryDataGetIn';
import type { HistoryDataGetOut } from '../models/HistoryDataGetOut';
import type { HistorySearchIn } from '../models/HistorySearchIn';
import type { HistorySearchOut } from '../models/HistorySearchOut';
import type { InfoOut } from '../models/InfoOut';
import type { OutBase } from '../models/OutBase';
import type { PlanCreateIn } from '../models/PlanCreateIn';
import type { PlanCreateOut } from '../models/PlanCreateOut';
import type { PlanDeleteIn } from '../models/PlanDeleteIn';
import type { PlanGetIn } from '../models/PlanGetIn';
import type { PlanGetOut } from '../models/PlanGetOut';
import type { PlanReorderIn } from '../models/PlanReorderIn';
import type { PlanUpdateIn } from '../models/PlanUpdateIn';
import type { QueueCreateOut } from '../models/QueueCreateOut';
import type { QueueDeleteIn } from '../models/QueueDeleteIn';
import type { QueueGetIn } from '../models/QueueGetIn';
import type { QueueGetOut } from '../models/QueueGetOut';
import type { QueueItemCreateOut } from '../models/QueueItemCreateOut';
import type { QueueItemDeleteIn } from '../models/QueueItemDeleteIn';
import type { QueueItemGetIn } from '../models/QueueItemGetIn';
import type { QueueItemGetOut } from '../models/QueueItemGetOut';
import type { QueueItemReorderIn } from '../models/QueueItemReorderIn';
import type { QueueItemUpdateIn } from '../models/QueueItemUpdateIn';
import type { QueueReorderIn } from '../models/QueueReorderIn';
import type { QueueSetInBase } from '../models/QueueSetInBase';
import type { QueueUpdateIn } from '../models/QueueUpdateIn';
import type { ScriptCreateIn } from '../models/ScriptCreateIn';
import type { ScriptCreateOut } from '../models/ScriptCreateOut';
import type { ScriptDeleteIn } from '../models/ScriptDeleteIn';
import type { ScriptGetIn } from '../models/ScriptGetIn';
import type { ScriptGetOut } from '../models/ScriptGetOut';
import type { ScriptReorderIn } from '../models/ScriptReorderIn';
import type { ScriptUpdateIn } from '../models/ScriptUpdateIn';
import type { SettingGetOut } from '../models/SettingGetOut';
import type { SettingUpdateIn } from '../models/SettingUpdateIn';
import type { TaskCreateIn } from '../models/TaskCreateIn';
import type { TaskCreateOut } from '../models/TaskCreateOut';
import type { TimeSetCreateOut } from '../models/TimeSetCreateOut';
import type { TimeSetDeleteIn } from '../models/TimeSetDeleteIn';
import type { TimeSetGetIn } from '../models/TimeSetGetIn';
import type { TimeSetGetOut } from '../models/TimeSetGetOut';
import type { TimeSetReorderIn } from '../models/TimeSetReorderIn';
import type { TimeSetUpdateIn } from '../models/TimeSetUpdateIn';
import type { UserCreateOut } from '../models/UserCreateOut';
import type { UserDeleteIn } from '../models/UserDeleteIn';
import type { UserGetIn } from '../models/UserGetIn';
import type { UserGetOut } from '../models/UserGetOut';
import type { UserInBase } from '../models/UserInBase';
import type { UserReorderIn } from '../models/UserReorderIn';
import type { UserUpdateIn } from '../models/UserUpdateIn';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class Service {
    /**
     * 获取关卡号下拉框信息
     * @param requestBody
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getStageComboxApiInfoComboxStagePost(
        requestBody: GetStageIn,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/combox/stage',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取脚本下拉框信息
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getScriptComboxApiInfoComboxScriptPost(): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/combox/script',
        });
    }
    /**
     * 获取可选任务下拉框信息
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getTaskComboxApiInfoComboxTaskPost(): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/combox/task',
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
     * 信息总览
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static addOverviewApiInfoGetOverviewPost(): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/get/overview',
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
     * 查询用户
     * @param requestBody
     * @returns UserGetOut Successful Response
     * @throws ApiError
     */
    public static getUserApiScriptsUserGetPost(
        requestBody: UserGetIn,
    ): CancelablePromise<UserGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/get',
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
     * 查询计划表
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
     * 查询定时项
     * @param requestBody
     * @returns TimeSetGetOut Successful Response
     * @throws ApiError
     */
    public static getTimeSetApiQueueTimeGetPost(
        requestBody: TimeSetGetIn,
    ): CancelablePromise<TimeSetGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/time/get',
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
     * 查询队列项
     * @param requestBody
     * @returns QueueItemGetOut Successful Response
     * @throws ApiError
     */
    public static getItemApiQueueItemGetPost(
        requestBody: QueueItemGetIn,
    ): CancelablePromise<QueueItemGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/queue/item/get',
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
     * 添加任务
     * @param requestBody
     * @returns TaskCreateOut Successful Response
     * @throws ApiError
     */
    public static addTaskApiDispatchStartPost(
        requestBody: TaskCreateIn,
    ): CancelablePromise<TaskCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/dispatch/start',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 中止任务
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static stopTaskApiDispatchStopPost(
        requestBody: DispatchIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/dispatch/stop',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 搜索历史记录总览信息
     * @param requestBody
     * @returns HistorySearchOut Successful Response
     * @throws ApiError
     */
    public static searchHistoryApiHistorySearchPost(
        requestBody: HistorySearchIn,
    ): CancelablePromise<HistorySearchOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/history/search',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 从指定文件内获取历史记录数据
     * @param requestBody
     * @returns HistoryDataGetOut Successful Response
     * @throws ApiError
     */
    public static getHistoryDataApiHistoryDataPost(
        requestBody: HistoryDataGetIn,
    ): CancelablePromise<HistoryDataGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/history/data',
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
