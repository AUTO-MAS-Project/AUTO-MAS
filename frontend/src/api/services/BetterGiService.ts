/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGICustomGroupsOut } from '../models/BetterGICustomGroupsOut';
import type { BetterGIDomainCatalogOut } from '../models/BetterGIDomainCatalogOut';
import type { BetterGIGlobalDomainSettingsIn } from '../models/BetterGIGlobalDomainSettingsIn';
import type { BetterGIGlobalDomainSettingsOut } from '../models/BetterGIGlobalDomainSettingsOut';
import type { BetterGIGlobalStygianSettingsIn } from '../models/BetterGIGlobalStygianSettingsIn';
import type { BetterGIGlobalStygianSettingsOut } from '../models/BetterGIGlobalStygianSettingsOut';
import type { BetterGIOneDragonSettingsIn } from '../models/BetterGIOneDragonSettingsIn';
import type { BetterGIOneDragonSettingsOut } from '../models/BetterGIOneDragonSettingsOut';
import type { BetterGIPathingTreeOut } from '../models/BetterGIPathingTreeOut';
import type { BetterGIScriptDirsOut } from '../models/BetterGIScriptDirsOut';
import type { BetterGIScriptGroupDetailOut } from '../models/BetterGIScriptGroupDetailOut';
import type { BetterGIScriptGroupSaveIn } from '../models/BetterGIScriptGroupSaveIn';
import type { BetterGIScriptReadmeOut } from '../models/BetterGIScriptReadmeOut';
import type { BetterGIScriptSettingsUiOut } from '../models/BetterGIScriptSettingsUiOut';
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
     * 返回秘境刷取配置（领奖树脂/分解圣遗物/奖励识别）。
     *
     * ``userId`` 非空时以该用户 per-user 副本为权威源（副本缺失回退 BGI 全局实配），
     * 使独立配置下每个用户的秘境刷取设置互不影响；``userId`` 为空（直控模式）读
     * BGI 全局 config.json（autoDomainConfig/autoArtifactSalvageConfig，camelCase）。
     * @param scriptId
     * @param userId
     * @returns BetterGIGlobalDomainSettingsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiGlobalDomainSettingsApiApiScriptsBettergiGlobalDomainSettingsGet(
        scriptId: string,
        userId: string = '',
    ): CancelablePromise<BetterGIGlobalDomainSettingsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/global-domain/settings',
            query: {
                'scriptId': scriptId,
                'userId': userId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存 BetterGI 全局 config.json 的秘境刷取配置段
     * 把右栏秘境刷取配置写回 per-user 副本；userId 为空（直控模式）写 BGI 全局 config.json。
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
     * 获取 BetterGI 全局 config.json 的自动幽境危战设置段
     * 返回自动幽境危战设置（刷取战场/战斗队伍/战斗策略/次数与树脂）。
     *
     * ``userId`` 非空时以该用户 per-user 副本为权威源（副本缺失回退 BGI 全局实配），
     * 使独立配置下每个用户的幽境设置互不影响；``userId`` 为空（直控模式）读
     * BGI 全局 config.json（autoStygianOnslaughtConfig 段，camelCase）。
     * @param scriptId
     * @param userId
     * @returns BetterGIGlobalStygianSettingsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiGlobalStygianSettingsApiApiScriptsBettergiGlobalStygianSettingsGet(
        scriptId: string,
        userId: string = '',
    ): CancelablePromise<BetterGIGlobalStygianSettingsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/global-stygian/settings',
            query: {
                'scriptId': scriptId,
                'userId': userId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存 BetterGI 全局 config.json 的自动幽境危战设置段
     * 把右栏自动幽境危战设置写回 per-user 副本；userId 为空（直控模式）写 BGI 全局 config.json。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static saveBettergiGlobalStygianSettingsApiApiScriptsBettergiGlobalStygianSettingsPost(
        requestBody: BetterGIGlobalStygianSettingsIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/bettergi/global-stygian/settings',
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
     * 数据源：官方传送点 tp.json（GameTask/AutoTrackPath/Assets/tp.json）中
     * Bless/Forgery/Mastery 三类 Domain 点（含奖励物）；tp.json 缺失或为空时返回空目录。
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
     * ``useMasConfig=True``（用户独立配置）时以 per-user 副本为权威源（固定「MAS独立配置」
     * 槽位名，副本缺失按内置模板），返回该用户将写入槽位的自定义组；``userId`` 必填。
     * 否则（非独立模式直控）读取 BGI ``{configName}`` 实配的自定义组。
     * @param scriptId
     * @param userId
     * @param configName
     * @param useMasConfig
     * @returns BetterGICustomGroupsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiCustomGroupsApiApiScriptsBettergiOneDragonCustomGroupsGet(
        scriptId: string,
        userId: string = '',
        configName: string = '',
        useMasConfig: boolean = false,
    ): CancelablePromise<BetterGICustomGroupsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/one-dragon/custom-groups',
            query: {
                'scriptId': scriptId,
                'userId': userId,
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
     * 返回 BetterGI 配置组候选：BGI ``User/ScriptGroup*.json`` 文件名；带 userId 时并集该用户 per-user 副本名。
     *
     * BetterGI 的「配置组」（GUI 中可加入一条龙的自定义任务组）以独立 json 保存于
     * ``User/ScriptGroup``，文件名（不含 ``.json``）即组名，与一条龙 TaskDefinitions
     * 的引用名一致。每次调用实时扫描，供「添加配置组」弹窗「配置组」标签页展示。
     *
     * ``userId`` 非空时把该用户的 per-user ScriptGroup 副本名一并并入（副本是 MAS
     * 独立配置的权威内容源，复制自 JS/路径等来源的新组也只存在于副本目录，需要能被
     * 识别/展示为配置组）。
     * @param scriptId
     * @param userId
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getBettergiScriptGroupsApiApiScriptsBettergiScriptGroupsGet(
        scriptId: string,
        userId: string = '',
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/script-groups',
            query: {
                'scriptId': scriptId,
                'userId': userId,
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
     * 该用户的 per-user 副本（``data/{script}/{user}/ScriptGroup/{name}.json``）。
     *
     * 不触碰 BetterGI 全局 ``User/ScriptGroup/{name}.json`` 同名实配。
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
