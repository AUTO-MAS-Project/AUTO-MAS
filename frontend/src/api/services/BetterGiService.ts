/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIDomainCatalogOut } from '../models/BetterGIDomainCatalogOut';
import type { BetterGICustomGroupsOut } from '../models/BetterGICustomGroupsOut';
import type { BetterGIScriptGroupDetailOut } from '../models/BetterGIScriptGroupDetailOut';
import type { BetterGIScriptGroupSaveIn } from '../models/BetterGIScriptGroupSaveIn';
import type { BetterGIScriptSettingsUiOut } from '../models/BetterGIScriptSettingsUiOut';
import type { BetterGIScriptReadmeOut } from '../models/BetterGIScriptReadmeOut';
import type { BetterGIGlobalDomainSettingsIn } from '../models/BetterGIGlobalDomainSettingsIn';
import type { BetterGIGlobalDomainSettingsOut } from '../models/BetterGIGlobalDomainSettingsOut';
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
     * 获取 BetterGI 全局 config.json 的秘境刷取配置段
     * 返回 BetterGI 全局 config.json 的秘境刷取配置（领奖树脂/分解圣遗物/奖励识别）。
     *
     * 该段存于 BGI 全局主配置（autoDomainConfig/autoArtifactSalvageConfig，camelCase），
     * 不随用户/一条龙配置组切换，故只按 scriptId 定位 RootPath 后读取。
     * @param scriptId
     * @returns BetterGIGlobalDomainSettingsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiGlobalDomainSettingsApiApiScriptsBettergiGlobalDomainSettingsGet(
        scriptId: string,
    ): CancelablePromise<BetterGIGlobalDomainSettingsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/global-domain/settings',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存 BetterGI 全局 config.json 的秘境刷取配置段
     * 把右栏秘境刷取配置写回 BetterGI 全局 config.json 的白名单键。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static saveBettergiGlobalDomainSettingsApiApiScriptsBettergiGlobalDomainSettingsPost(
        requestBody: BetterGIGlobalDomainSettingsIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/bettergi/global-domain/settings',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 BetterGI 每周秘境候选与每秘境三档奖励物
     * 返回 BetterGI 每周秘境可选秘境目录与分档奖励物。
     *
     * 秘境名以官方传送点 tp.json（GameTask/AutoTrackPath/Assets）为准；
     * 产出表 Genshin_Domains_SC_Live_Source.json（用户 JS 脚本目录下）仅补三档奖励物名。
     * 供「每周秘境」表格的秘境/奖励下拉联动使用（奖励仍按 BGI 语义存 0~3 序号）。
     * @param scriptId
     * @returns BetterGIDomainCatalogOut Successful Response
     * @throws ApiError
     */
    public static getBettergiDomainCatalogApiApiScriptsBettergiDomainCatalogGet(
        scriptId: string,
    ): CancelablePromise<BetterGIDomainCatalogOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/domain-catalog',
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
     * 获取 BetterGI 可用配置组列表
     * 返回 BetterGI 配置组候选：{RootPath}/User/ScriptGroup*.json 的文件名。
     *
     * BetterGI 的「配置组」（GUI 中可加入一条龙的自定义任务组）以独立 json 保存于
     * ``User/ScriptGroup``，文件名（不含 ``.json``）即组名，与一条龙 TaskDefinitions
     * 的引用名一致。供「添加配置组」弹窗「配置组」标签页展示。
     * @param scriptId
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getBettergiScriptGroupsApiApiScriptsBettergiScriptGroupsGet(
        scriptId: string,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/script-groups',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 BetterGI 配置组 json 详情（per-user 副本优先）
     * 返回某用户的配置组 json（per-user 副本 → BGI 实配的种子顺序）。
     *
     * 右栏「配置组」标签页选中 scriptgroup 时，据此列出其 json 内 ``projects`` 的
     * 每个项目；也供 JS/路径等单项目组展示（项目名=组名）。
     * @param scriptId
     * @param userId
     * @param name
     * @returns BetterGIScriptGroupDetailOut Successful Response
     * @throws ApiError
     */
    public static getBettergiScriptGroupDetailApiApiScriptsBettergiScriptGroupDetailGet(
        scriptId: string,
        userId: string,
        name: string,
    ): CancelablePromise<BetterGIScriptGroupDetailOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/script-group/detail',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'name': name,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存 BetterGI 配置组 json 到 per-user 副本
     * 把右栏编辑后的配置组 json（项目顺序 + 各项目 jsScriptSettingsObject）写回
     * 该用户的 per-user 副本。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static saveBettergiScriptGroupApiApiScriptsBettergiScriptGroupSavePost(
        requestBody: BetterGIScriptGroupSaveIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/bettergi/script-group/save',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 BetterGI 某 JsScript 脚本目录的 settings.json UI 定义
     * 返回某脚本目录（User/JsScript/{folder}/）的 settings.json UI 定义数组。
     *
     * 双击配置组内某项目（其 folderName 即脚本目录名）时，前端据此渲染设置弹窗表单。
     * @param scriptId
     * @param folder
     * @returns BetterGIScriptSettingsUiOut Successful Response
     * @throws ApiError
     */
    public static getBettergiScriptSettingsUiApiApiScriptsBettergiScriptSettingsUiGet(
        scriptId: string,
        folder: string,
    ): CancelablePromise<BetterGIScriptSettingsUiOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/script-settings-ui',
            query: {
                'scriptId': scriptId,
                'folder': folder,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 BetterGI 某 JsScript 脚本目录的 README 内容
     * 返回某脚本目录（User/JsScript/{folder}/）的 README 纯文本。
     *
     * 双击配置组内某项目设置弹窗的「脚本说明」标签页展示。
     * @param scriptId
     * @param folder
     * @returns BetterGIScriptReadmeOut Successful Response
     * @throws ApiError
     */
    public static getBettergiScriptReadmeApiApiScriptsBettergiScriptReadmeGet(
        scriptId: string,
        folder: string,
    ): CancelablePromise<BetterGIScriptReadmeOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/script-readme',
            query: {
                'scriptId': scriptId,
                'folder': folder,
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
