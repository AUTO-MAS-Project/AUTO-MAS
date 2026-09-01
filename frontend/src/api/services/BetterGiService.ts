/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGICustomGroupsOut } from '../models/BetterGICustomGroupsOut';
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class BetterGiService {
    /**
     * 获取 BetterGI 自动战斗策略选项
     * 返回 BetterGI 可用自动战斗策略：内置「根据队伍自动选择」+ ``{RootPath}/User/AutoFight*.txt`` 文件名。
     * @param scriptId
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getBettergiStrategiesApiApiScriptsBettergiStrategiesGet(
        scriptId: string,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/strategies',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 BetterGI 一条龙自定义配置组
     * 返回指定一条龙配置里的自定义配置组（非内置 8 组）及其启用状态，供前端表格自动加载。
     *
     * ``useMasConfig=True``（用户独立配置）时改读 MAS 运行时槽位「MAS独立配置」：独立模式的
     * per-user 配置物化在槽位而非 {configName} 实配，读槽位才能列到用户刚在 BGI GUI 里往
     * 独立配置添加的自定义组。
     * @param scriptId
     * @param configName
     * @param useMasConfig
     * @returns BetterGICustomGroupsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiCustomGroupsApiApiScriptsBettergiOneDragonCustomGroupsGet(
        scriptId: string,
        configName: string = '',
        useMasConfig: boolean = false,
    ): CancelablePromise<BetterGICustomGroupsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/one-dragon/custom-groups',
            query: {
                'scriptId': scriptId,
                'configName': configName,
                'useMasConfig': useMasConfig,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 BetterGI 一条龙配置名列表
     * 返回 BetterGI 可选一条龙配置名：{RootPath}/User/OneDragon*.json 文件名（默认配置置顶）。
     * @param scriptId
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getBettergiOneDragonConfigsApiApiScriptsBettergiOneDragonConfigsGet(
        scriptId: string,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/one-dragon/configs',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
