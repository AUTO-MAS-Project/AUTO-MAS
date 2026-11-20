/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameCalendarActivityCompletionIn } from '../models/GameCalendarActivityCompletionIn';
import type { OkwwPlanConfigsIn } from '../models/OkwwPlanConfigsIn';
import type { OkwwTaskConfigIn } from '../models/OkwwTaskConfigIn';
import type { OutBase } from '../models/OutBase';
import type { TaskboardArchiveIn } from '../models/TaskboardArchiveIn';
import type { TaskboardDoneAtIn } from '../models/TaskboardDoneAtIn';
import type { TaskboardSelectionIn } from '../models/TaskboardSelectionIn';
import type { TaskboardVersionStoryIn } from '../models/TaskboardVersionStoryIn';
import type { TaskboardWeeklyIn } from '../models/TaskboardWeeklyIn';
import type { TaskboardWeeklyOut } from '../models/TaskboardWeeklyOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SetService {
    /**
     * 设置游戏活动完成状态
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setActivityCompletionApiInfoActivityCompletionsPost(
        requestBody: GameCalendarActivityCompletionIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/activity/completions',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存任务台勾选的游戏
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setTaskboardSelectionApiInfoTaskboardSelectionPut(
        requestBody: TaskboardSelectionIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/info/taskboard/selection',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存每周任务勾选的游戏
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setTaskboardWeeklySelectionApiInfoTaskboardWeeklySelectionPut(
        requestBody: TaskboardSelectionIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/info/taskboard/weekly-selection',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存任务台归档缓存
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setTaskboardArchiveApiInfoTaskboardArchivePut(
        requestBody: TaskboardArchiveIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/info/taskboard/archive',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 记录或删除任务台的完成日期
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setTaskboardDoneAtApiInfoTaskboardDoneAtPut(
        requestBody: TaskboardDoneAtIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/info/taskboard/done-at',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 记录或撤销任务台的每周任务
     * @param requestBody
     * @returns TaskboardWeeklyOut Successful Response
     * @throws ApiError
     */
    public static setTaskboardWeeklyApiInfoTaskboardWeeklyPut(
        requestBody: TaskboardWeeklyIn,
    ): CancelablePromise<TaskboardWeeklyOut> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/info/taskboard/weekly',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 合并任务台的版本主线记录
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setTaskboardVersionStoryApiInfoTaskboardVersionStoryPut(
        requestBody: TaskboardVersionStoryIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/info/taskboard/version-story',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 记录或撤销任务台的版本主线完成状态
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setTaskboardVersionStoryDoneApiInfoTaskboardVersionStoryDonePut(
        requestBody: TaskboardDoneAtIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/info/taskboard/version-story/done',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Save Okww Task Config Api
     * 保存面板及已有日常字段，不修改基础来源。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static saveOkwwTaskConfigApiApiScriptsOkwwTaskConfigPost(
        requestBody: OkwwTaskConfigIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okww/task-config',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Save Okww Plan Configs Api
     * 替换当天覆写，未设置项恢复继承账号配置。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static saveOkwwPlanConfigsApiApiScriptsOkwwPlanConfigsPost(
        requestBody: OkwwPlanConfigsIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okww/plan/configs',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
