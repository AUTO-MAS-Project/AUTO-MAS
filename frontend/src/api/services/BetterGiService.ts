/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGICustomGroupsOut } from '../models/BetterGICustomGroupsOut';
import type { BetterGIOneDragonSettingsIn } from '../models/BetterGIOneDragonSettingsIn';
import type { BetterGIOneDragonSettingsOut } from '../models/BetterGIOneDragonSettingsOut';
import type { BetterGIPathingTreeOut } from '../models/BetterGIPathingTreeOut';
import type { BetterGIScriptDirsOut } from '../models/BetterGIScriptDirsOut';
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { OutBase } from '../models/OutBase';
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
     * 获取 BetterGI 一条龙设置项（右栏按任务分组展示）
     * 返回某用户一条龙配置的设置项（per-user 副本 → BGI 实配 → 内置模板的种子顺序）。
     *
     * 供右栏按任务分组渲染并回显该任务在 BGI 一条龙里的可设置字段。
     * @param scriptId
     * @param userId
     * @param configName
     * @returns BetterGIOneDragonSettingsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiOneDragonSettingsApiApiScriptsBettergiOneDragonSettingsGet(
        scriptId: string,
        userId: string,
        configName: string = '',
    ): CancelablePromise<BetterGIOneDragonSettingsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/one-dragon/settings',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'configName': configName,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存 BetterGI 一条龙设置项到 per-user 副本
     * 把右栏编辑的设置项写回该用户一条龙配置副本（不触碰 BGI 同名实配）。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static saveBettergiOneDragonSettingsApiApiScriptsBettergiOneDragonSettingsPost(
        requestBody: BetterGIOneDragonSettingsIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/bettergi/one-dragon/settings',
            body: requestBody,
            mediaType: 'application/json',
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
    /**
     * 获取 BetterGI 可用自定义 JS 脚本列表
     * 返回 BetterGI 可执行自定义 JS 脚本候选。
     *
     * ``label`` 为 ``manifest.json`` 的中文显示名（目录名常为英文，如
     * ``AAA-Artifacts-Bulk-Supply`` → 「AAA狗粮批发」）；``value`` 为脚本**目录名**
     * （BetterGI 一条龙按目录名定位任务，落库与执行都用它）。
     * 供一条龙「添加配置组」弹窗作为候选（贴 JS 标签）选择。
     * @param scriptId
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getBettergiJsScriptsApiApiScriptsBettergiJsScriptsGet(
        scriptId: string,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/js-scripts',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 BetterGI 常用目录（脚本仓库 / JsScript / AutoPathing）
     * 返回 BetterGI 三个常用目录的绝对路径，供「添加配置组」弹窗的打开目录按钮使用。
     * @param scriptId
     * @returns BetterGIScriptDirsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiScriptDirsApiApiScriptsBettergiDirsGet(
        scriptId: string,
    ): CancelablePromise<BetterGIScriptDirsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/dirs',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 BetterGI 地图追踪目录树
     * 返回 BetterGI 地图追踪目录树：{RootPath}/User/AutoPathing 的递归结构。
     *
     * 节点：``{name, dirs, files}``，``files`` 为路径文件名（不含 ``.json``、含相对目录前缀），
     * 全局唯一。供「添加配置组」弹窗「地图追踪」标签页左树右表浏览。
     * @param scriptId
     * @returns BetterGIPathingTreeOut Successful Response
     * @throws ApiError
     */
    public static getBettergiAutoPathingTreeApiApiScriptsBettergiAutoPathingTreeGet(
        scriptId: string,
    ): CancelablePromise<BetterGIPathingTreeOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/auto-pathing-tree',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
