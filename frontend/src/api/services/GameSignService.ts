/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameSignAccountCreateOut } from '../models/GameSignAccountCreateOut';
import type { GameSignAccountDeleteIn } from '../models/GameSignAccountDeleteIn';
import type { GameSignAccountGetIn } from '../models/GameSignAccountGetIn';
import type { GameSignAccountReorderIn } from '../models/GameSignAccountReorderIn';
import type { GameSignAccountsListOut } from '../models/GameSignAccountsListOut';
import type { GameSignAccountUpdateIn } from '../models/GameSignAccountUpdateIn';
import type { OutBase } from '../models/OutBase';
import type { SklandLoginIn } from '../models/SklandLoginIn';
import type { TaygedoLoginIn } from '../models/TaygedoLoginIn';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class GameSignService {
    /**
     * 获取所有游戏社区账号组
     * 获取所有游戏社区账号组
     * @returns GameSignAccountsListOut Successful Response
     * @throws ApiError
     */
    public static listGameSignAccountsApiToolsSignAccountListPost(): CancelablePromise<GameSignAccountsListOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/account/list',
        });
    }
    /**
     * 添加游戏社区账号组
     * 添加游戏社区账号组
     * @returns GameSignAccountCreateOut Successful Response
     * @throws ApiError
     */
    public static addGameSignAccountApiToolsSignAccountAddPost(): CancelablePromise<GameSignAccountCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/account/add',
        });
    }
    /**
     * 获取游戏社区账号组详情
     * 获取游戏社区账号组详情
     * @param requestBody
     * @returns GameSignAccountCreateOut Successful Response
     * @throws ApiError
     */
    public static getGameSignAccountApiToolsSignAccountGetPost(
        requestBody: GameSignAccountGetIn,
    ): CancelablePromise<GameSignAccountCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/account/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新游戏社区账号组配置
     * 更新游戏社区账号组配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateGameSignAccountApiToolsSignAccountUpdatePost(
        requestBody: GameSignAccountUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/account/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除游戏社区账号组
     * 删除游戏社区账号组
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteGameSignAccountApiToolsSignAccountDeletePost(
        requestBody: GameSignAccountDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/account/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 调整游戏社区账号组顺序
     * 调整游戏社区账号组顺序
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderGameSignAccountsApiToolsSignAccountReorderPost(
        requestBody: GameSignAccountReorderIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/account/reorder',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 塔吉多账号密码登录
     * 一次性使用账号密码换取并保存塔吉多 Token，不保存密码。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static loginTaygedoApiToolsSignAccountTaygedoLoginPost(
        requestBody: TaygedoLoginIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/account/taygedo/login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 森空岛手机号密码登录
     * 一次性使用手机号和密码换取并保存森空岛凭据，不保存密码。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static loginSklandApiToolsSignAccountSklandLoginPost(
        requestBody: SklandLoginIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/account/skland/login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
