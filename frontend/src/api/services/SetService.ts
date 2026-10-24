/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameCalendarActivityCompletionIn } from '../models/GameCalendarActivityCompletionIn';
import type { OutBase } from '../models/OutBase';
import type { TaskboardArchiveIn } from '../models/TaskboardArchiveIn';
import type { TaskboardDoneAtIn } from '../models/TaskboardDoneAtIn';
import type { TaskboardSelectionIn } from '../models/TaskboardSelectionIn';
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
}
