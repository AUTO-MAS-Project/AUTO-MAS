/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AbyssSnapshotImportOut } from '../models/AbyssSnapshotImportOut';
import type { Body_batch_update_okww_configs_api_scripts_okww_configs_batch_update_post } from '../models/Body_batch_update_okww_configs_api_scripts_okww_configs_batch_update_post';
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { DispatchIn } from '../models/DispatchIn';
import type { EmulatorCreateOut } from '../models/EmulatorCreateOut';
import type { EmulatorDeleteIn } from '../models/EmulatorDeleteIn';
import type { EmulatorGetIn } from '../models/EmulatorGetIn';
import type { EmulatorGetOut } from '../models/EmulatorGetOut';
import type { EmulatorOperateIn } from '../models/EmulatorOperateIn';
import type { EmulatorReorderIn } from '../models/EmulatorReorderIn';
import type { EmulatorSearchOut } from '../models/EmulatorSearchOut';
import type { EmulatorStatusOut } from '../models/EmulatorStatusOut';
import type { EmulatorUpdateIn } from '../models/EmulatorUpdateIn';
import type { GameAddIn } from '../models/GameAddIn';
import type { GameCheckOut } from '../models/GameCheckOut';
import type { GameCreateOut } from '../models/GameCreateOut';
import type { GameDeleteIn } from '../models/GameDeleteIn';
import type { GameGetIn } from '../models/GameGetIn';
import type { GameGetOut } from '../models/GameGetOut';
import type { GameInstallLocalApkIn } from '../models/GameInstallLocalApkIn';
import type { GameOperateIn } from '../models/GameOperateIn';
import type { GamePresetsOut } from '../models/GamePresetsOut';
import type { GameReorderIn } from '../models/GameReorderIn';
import type { GameSignAccountCreateOut } from '../models/GameSignAccountCreateOut';
import type { GameSignAccountDeleteIn } from '../models/GameSignAccountDeleteIn';
import type { GameSignAccountGetIn } from '../models/GameSignAccountGetIn';
import type { GameSignAccountReorderIn } from '../models/GameSignAccountReorderIn';
import type { GameSignAccountsListOut } from '../models/GameSignAccountsListOut';
import type { GameSignAccountUpdateIn } from '../models/GameSignAccountUpdateIn';
import type { GameTaskStatusOut } from '../models/GameTaskStatusOut';
import type { GameUpdateIn } from '../models/GameUpdateIn';
import type { GetStageIn } from '../models/GetStageIn';
import type { HistoryDataGetIn } from '../models/HistoryDataGetIn';
import type { HistoryDataGetOut } from '../models/HistoryDataGetOut';
import type { HistorySearchIn } from '../models/HistorySearchIn';
import type { HistorySearchOut } from '../models/HistorySearchOut';
import type { HSRStageOptionsOut } from '../models/HSRStageOptionsOut';
import type { InfoOut } from '../models/InfoOut';
import type { MaaFWAgentEnvPrepareIn } from '../models/MaaFWAgentEnvPrepareIn';
import type { MaaFWAgentEnvPrepareOut } from '../models/MaaFWAgentEnvPrepareOut';
import type { MaaFWInterfacePreviewIn } from '../models/MaaFWInterfacePreviewIn';
import type { MaaFWInterfacePreviewOut } from '../models/MaaFWInterfacePreviewOut';
import type { MaaFWProjectUpdateIn } from '../models/MaaFWProjectUpdateIn';
import type { MaaFWProjectUpdateOut } from '../models/MaaFWProjectUpdateOut';
import type { MaaFWWindowPreviewIn } from '../models/MaaFWWindowPreviewIn';
import type { MaaFWWindowPreviewOut } from '../models/MaaFWWindowPreviewOut';
import type { NoticeOut } from '../models/NoticeOut';
import type { OutBase } from '../models/OutBase';
import type { PlanCreateIn } from '../models/PlanCreateIn';
import type { PlanCreateOut } from '../models/PlanCreateOut';
import type { PlanDeleteIn } from '../models/PlanDeleteIn';
import type { PlanGetIn } from '../models/PlanGetIn';
import type { PlanGetOut } from '../models/PlanGetOut';
import type { PlanReorderIn } from '../models/PlanReorderIn';
import type { PlanUpdateIn } from '../models/PlanUpdateIn';
import type { PluginAddIn } from '../models/PluginAddIn';
import type { PluginAddOut } from '../models/PluginAddOut';
import type { PluginDeleteIn } from '../models/PluginDeleteIn';
import type { PluginFrontendBackgroundOut } from '../models/PluginFrontendBackgroundOut';
import type { PluginPackageIn } from '../models/PluginPackageIn';
import type { PluginReloadInstanceIn } from '../models/PluginReloadInstanceIn';
import type { PluginReloadPluginIn } from '../models/PluginReloadPluginIn';
import type { PluginsGetOut } from '../models/PluginsGetOut';
import type { PluginUpdateIn } from '../models/PluginUpdateIn';
import type { PowerIn } from '../models/PowerIn';
import type { PowerOut } from '../models/PowerOut';
import type { QrCheckIn } from '../models/QrCheckIn';
import type { QrCheckOut } from '../models/QrCheckOut';
import type { QrCreateOut } from '../models/QrCreateOut';
import type { QrSaveIn } from '../models/QrSaveIn';
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
import type { ScriptConfigImportIn } from '../models/ScriptConfigImportIn';
import type { ScriptCreateIn } from '../models/ScriptCreateIn';
import type { ScriptCreateOut } from '../models/ScriptCreateOut';
import type { ScriptDeleteIn } from '../models/ScriptDeleteIn';
import type { ScriptFileIn } from '../models/ScriptFileIn';
import type { ScriptGetIn } from '../models/ScriptGetIn';
import type { ScriptGetOut } from '../models/ScriptGetOut';
import type { ScriptRecordCreateIn } from '../models/ScriptRecordCreateIn';
import type { ScriptRecordCreateOut } from '../models/ScriptRecordCreateOut';
import type { ScriptRecordDeleteIn } from '../models/ScriptRecordDeleteIn';
import type { ScriptRecordGetIn } from '../models/ScriptRecordGetIn';
import type { ScriptRecordGetOut } from '../models/ScriptRecordGetOut';
import type { ScriptRecordReorderIn } from '../models/ScriptRecordReorderIn';
import type { ScriptRecordUpdateIn } from '../models/ScriptRecordUpdateIn';
import type { ScriptReorderIn } from '../models/ScriptReorderIn';
import type { ScriptTypeGetOut } from '../models/ScriptTypeGetOut';
import type { ScriptUpdateIn } from '../models/ScriptUpdateIn';
import type { ScriptUploadIn } from '../models/ScriptUploadIn';
import type { ScriptUrlIn } from '../models/ScriptUrlIn';
import type { ScriptUserRecordCreateIn } from '../models/ScriptUserRecordCreateIn';
import type { ScriptUserRecordCreateOut } from '../models/ScriptUserRecordCreateOut';
import type { ScriptUserRecordDeleteIn } from '../models/ScriptUserRecordDeleteIn';
import type { ScriptUserRecordGetIn } from '../models/ScriptUserRecordGetIn';
import type { ScriptUserRecordGetOut } from '../models/ScriptUserRecordGetOut';
import type { ScriptUserRecordReorderIn } from '../models/ScriptUserRecordReorderIn';
import type { ScriptUserRecordUpdateIn } from '../models/ScriptUserRecordUpdateIn';
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
import type { ToolsGetOut } from '../models/ToolsGetOut';
import type { ToolsUpdateIn } from '../models/ToolsUpdateIn';
import type { UpdateCheckIn } from '../models/UpdateCheckIn';
import type { UpdateCheckOut } from '../models/UpdateCheckOut';
import type { UserCreateOut } from '../models/UserCreateOut';
import type { UserDeleteIn } from '../models/UserDeleteIn';
import type { UserGetIn } from '../models/UserGetIn';
import type { UserGetOut } from '../models/UserGetOut';
import type { UserImportAbyssSnapshotIn } from '../models/UserImportAbyssSnapshotIn';
import type { UserInBase } from '../models/UserInBase';
import type { UserReorderIn } from '../models/UserReorderIn';
import type { UserSetIn } from '../models/UserSetIn';
import type { UserUpdateIn } from '../models/UserUpdateIn';
import type { VersionOut } from '../models/VersionOut';
import type { WebhookCreateOut } from '../models/WebhookCreateOut';
import type { WebhookDeleteIn } from '../models/WebhookDeleteIn';
import type { WebhookGetIn } from '../models/WebhookGetIn';
import type { WebhookGetOut } from '../models/WebhookGetOut';
import type { WebhookInBase } from '../models/WebhookInBase';
import type { WebhookReorderIn } from '../models/WebhookReorderIn';
import type { WebhookTestIn } from '../models/WebhookTestIn';
import type { WebhookUpdateIn } from '../models/WebhookUpdateIn';
import type { WebSocketMetaOut } from '../models/WebSocketMetaOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class Service {
    /**
     * 获取主 WebSocket 元信息
     * 返回前端建立主 WebSocket 连接需要的元信息。
     * @returns WebSocketMetaOut Successful Response
     * @throws ApiError
     */
    public static getWsMetaApiCoreWsMetaGet(): CancelablePromise<WebSocketMetaOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/core/ws_meta',
        });
    }
    /**
     * 关闭后端程序
     * 关闭后端程序
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static closeApiCoreClosePost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/core/close',
        });
    }
    /**
     * 获取后端git版本信息
     * @returns VersionOut Successful Response
     * @throws ApiError
     */
    public static getGitVersionApiInfoVersionPost(): CancelablePromise<VersionOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/version',
        });
    }
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
     * 获取可选计划下拉框信息
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getPlanComboxApiInfoComboxPlanPost(): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/combox/plan',
        });
    }
    /**
     * 获取可选模拟器下拉框信息
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getEmulatorComboxApiInfoComboxEmulatorPost(): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/combox/emulator',
        });
    }
    /**
     * 获取可选模拟器多开实例下拉框信息
     * @param requestBody
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost(
        requestBody: EmulatorDeleteIn,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/combox/emulator/devices',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取通知信息
     * @returns NoticeOut Successful Response
     * @throws ApiError
     */
    public static getNoticeInfoApiInfoNoticeGetPost(): CancelablePromise<NoticeOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/notice/get',
        });
    }
    /**
     * 确认通知
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static confirmNoticeApiInfoNoticeConfirmPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/notice/confirm',
        });
    }
    /**
     * 获取配置分享中心的配置信息
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static getWebConfigApiInfoWebconfigPost(): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/webconfig',
        });
    }
    /**
     * 信息总览
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static getOverviewApiInfoGetOverviewPost(): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/get/overview',
        });
    }
    /**
     * 查询模拟器配置
     * @param requestBody
     * @returns EmulatorGetOut Successful Response
     * @throws ApiError
     */
    public static getEmulatorApiEmulatorGetPost(
        requestBody: EmulatorGetIn,
    ): CancelablePromise<EmulatorGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加模拟器项
     * @returns EmulatorCreateOut Successful Response
     * @throws ApiError
     */
    public static addEmulatorApiEmulatorAddPost(): CancelablePromise<EmulatorCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/add',
        });
    }
    /**
     * 更新模拟器项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateEmulatorApiEmulatorUpdatePost(
        requestBody: EmulatorUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/update',
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
     * 重新排序模拟器项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderEmulatorApiEmulatorOrderPost(
        requestBody: EmulatorReorderIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 操作模拟器
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static operationEmulatorApiEmulatorOperatePost(
        requestBody: EmulatorOperateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/operate',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询模拟器状态
     * @param requestBody
     * @returns EmulatorStatusOut Successful Response
     * @throws ApiError
     */
    public static getStatusApiEmulatorStatusPost(
        requestBody: EmulatorGetIn,
    ): CancelablePromise<EmulatorStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/status',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 搜索已安装的模拟器
     * 自动搜索系统中已安装的模拟器
     * @returns EmulatorSearchOut Successful Response
     * @throws ApiError
     */
    public static searchEmulatorsApiEmulatorEmulatorSearchPost(): CancelablePromise<EmulatorSearchOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator/emulator/search',
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
    public static getScriptApiScriptsGetPost(
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
     * 从文件加载脚本配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static importScriptFromFileApiScriptsImportFilePost(
        requestBody: ScriptFileIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/import/file',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 导出脚本配置到文件
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static exportScriptToFileApiScriptsExportFilePost(
        requestBody: ScriptFileIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/export/file',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 从网络加载脚本配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static importScriptFromWebApiScriptsImportWebPost(
        requestBody: ScriptUrlIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/import/web',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 上传脚本配置到网络
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static uploadScriptToWebApiScriptsUploadWebPost(
        requestBody: ScriptUploadIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/Upload/web',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 从脚本目录导入配置文件
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static importScriptConfigFileApiScriptsConfigImportPost(
        requestBody: ScriptConfigImportIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/config/import',
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
     * 从 M7A config.yaml 导入三深渊快照
     * 从 M7A config.yaml 读取三深渊白名单字段，写入指定 HSR 用户配置。
     * @param requestBody
     * @returns AbyssSnapshotImportOut Successful Response
     * @throws ApiError
     */
    public static importM7AAbyssSnapshotApiScriptsUserImportM7AAbyssSnapshotPost(
        requestBody: UserImportAbyssSnapshotIn,
    ): CancelablePromise<AbyssSnapshotImportOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/import-m7a-abyss-snapshot',
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
     * 导入基建配置文件
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static importInfrastructureApiScriptsUserInfrastructurePost(
        requestBody: UserSetIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/infrastructure',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 用户自定义基建排班可选项
     * @param requestBody
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getUserComboxInfrastructureApiScriptsUserComboxInfrastructurePost(
        requestBody: UserDeleteIn,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/combox/infrastructure',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询 webhook 配置
     * @param requestBody
     * @returns WebhookGetOut Successful Response
     * @throws ApiError
     */
    public static getWebhookApiScriptsWebhookGetPost(
        requestBody: WebhookGetIn,
    ): CancelablePromise<WebhookGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/webhook/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加webhook项
     * @param requestBody
     * @returns WebhookCreateOut Successful Response
     * @throws ApiError
     */
    public static addWebhookApiScriptsWebhookAddPost(
        requestBody: WebhookInBase,
    ): CancelablePromise<WebhookCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/webhook/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新webhook项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateWebhookApiScriptsWebhookUpdatePost(
        requestBody: WebhookUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/webhook/update',
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
     * 重新排序webhook项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderWebhookApiScriptsWebhookOrderPost(
        requestBody: WebhookReorderIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/webhook/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 M9A 可用任务列表（排除 standalone 任务）
     * 获取 M9A 可用任务列表（排除 standalone 任务）
     *
     * 前端调用此接口获取可选择的任务列表，
     * 用于展示在用户编辑界面的任务选择区域。
     *
     * Args:
     * script_id: M9A 脚本 ID
     *
     * Returns:
     * dict: 包含任务列表的响应
     * @param scriptId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getM9AAvailableTasksApiScriptsM9ATasksAvailablePost(
        scriptId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/m9a/tasks/available',
            query: {
                'script_id': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 预览 MaaFW ProjectInterface
     * 读取 MaaFW 项目目录中的 interface.json，返回 MAS UI 可消费的摘要。
     * @param requestBody
     * @returns MaaFWInterfacePreviewOut Successful Response
     * @throws ApiError
     */
    public static previewMaafwInterfaceApiScriptsMaafwInterfacePreviewPost(
        requestBody: MaaFWInterfacePreviewIn,
    ): CancelablePromise<MaaFWInterfacePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/interface/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 手动更新 MaaFW 项目资源
     * 按脚本更新配置手动检查并应用 MaaFW 项目资源更新。
     * @param requestBody
     * @returns MaaFWProjectUpdateOut Successful Response
     * @throws ApiError
     */
    public static updateMaafwProjectApiScriptsMaafwProjectUpdatePost(
        requestBody: MaaFWProjectUpdateIn,
    ): CancelablePromise<MaaFWProjectUpdateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/project/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Prepare MaaFW runtime env
     * Prepare MaaFW Runner and agent Python envs before starting tasks.
     * @param requestBody
     * @returns MaaFWAgentEnvPrepareOut Successful Response
     * @throws ApiError
     */
    public static prepareMaafwAgentEnvApiScriptsMaafwAgentEnvPreparePost(
        requestBody: MaaFWAgentEnvPrepareIn,
    ): CancelablePromise<MaaFWAgentEnvPrepareOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/agent-env/prepare',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 读取 MaaFW 本地图片资源
     * 读取 MaaFW interface 描述、任务、选项中引用的本地图片资源。
     * @param root MaaFW 项目根目录
     * @param path 相对 MaaFW 项目根目录的图片路径
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getMaafwAssetApiScriptsMaafwAssetGet(
        root: string,
        path: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/maafw/asset',
            query: {
                'root': root,
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 扫描 MaaFW PC 客户端窗口
     * 按 interface.json 中的 Win32 窗口规则扫描本机桌面窗口。
     * @param requestBody
     * @returns MaaFWWindowPreviewOut Successful Response
     * @throws ApiError
     */
    public static previewMaafwWindowsApiScriptsMaafwWindowsPreviewPost(
        requestBody: MaaFWWindowPreviewIn,
    ): CancelablePromise<MaaFWWindowPreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/windows/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 HSR 体力副本动态选项
     * 按体力执行脚本返回 M7A / SRA 原生副本字段。
     * @param scriptId
     * @param engine
     * @returns HSRStageOptionsOut Successful Response
     * @throws ApiError
     */
    public static getHsrStageOptionsApiApiScriptsHsrStageOptionsGet(
        scriptId?: (string | null),
        engine: 'M7A' | 'SRA' = 'M7A',
    ): CancelablePromise<HSRStageOptionsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/stage-options',
            query: {
                'scriptId': scriptId,
                'engine': engine,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 OK-WW 配置文件列表及 schema
     * 获取 OK-WW 配置文件列表及 schema 定义。
     * 读写用户配置目录（data/{script_id}/{user_id}/ConfigFile/），
     * 若为空则自动从 ok-ww configs 目录初始化默认配置。
     *
     * Args:
     * script_id: OK-WW 脚本 ID
     * user_id: 用户 ID
     *
     * Returns:
     * dict: 包含配置文件列表和 schema 的响应
     * @param scriptId
     * @param userId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getOkwwConfigsListApiScriptsOkwwConfigsListPost(
        scriptId: string,
        userId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okww/configs/list',
            query: {
                'script_id': scriptId,
                'user_id': userId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量更新 OK-WW 配置文件
     * 批量更新 OK-WW 配置文件
     *
     * Args:
     * script_id: OK-WW 脚本 ID
     * user_id: 用户 ID
     * configs: { filename: data } 格式的配置数据
     *
     * Returns:
     * dict: 操作结果
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static batchUpdateOkwwConfigsApiScriptsOkwwConfigsBatchUpdatePost(
        requestBody: Body_batch_update_okww_configs_api_scripts_okww_configs_batch_update_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/okww/configs/batch-update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加脚本
     * @param requestBody
     * @returns ScriptRecordCreateOut Successful Response
     * @throws ApiError
     */
    public static addScriptApiScripts2AddPost(
        requestBody: ScriptRecordCreateIn,
    ): CancelablePromise<ScriptRecordCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取脚本
     * @param requestBody
     * @returns ScriptRecordGetOut Successful Response
     * @throws ApiError
     */
    public static getScriptApiScripts2GetPost(
        requestBody: ScriptRecordGetIn,
    ): CancelablePromise<ScriptRecordGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新脚本
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateScriptApiScripts2UpdatePost(
        requestBody: ScriptRecordUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/update',
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
    public static deleteScriptApiScripts2DeletePost(
        requestBody: ScriptRecordDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 脚本排序
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderScriptApiScripts2OrderPost(
        requestBody: ScriptRecordReorderIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取用户
     * @param requestBody
     * @returns ScriptUserRecordGetOut Successful Response
     * @throws ApiError
     */
    public static getUsersApiScripts2UsersGetPost(
        requestBody: ScriptUserRecordGetIn,
    ): CancelablePromise<ScriptUserRecordGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/users/get',
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
     * @returns ScriptUserRecordCreateOut Successful Response
     * @throws ApiError
     */
    public static addUserApiScripts2UsersAddPost(
        requestBody: ScriptUserRecordCreateIn,
    ): CancelablePromise<ScriptUserRecordCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/users/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新用户
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateUserApiScripts2UsersUpdatePost(
        requestBody: ScriptUserRecordUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/users/update',
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
    public static deleteUserApiScripts2UsersDeletePost(
        requestBody: ScriptUserRecordDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/users/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 用户排序
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderUserApiScripts2UsersOrderPost(
        requestBody: ScriptUserRecordReorderIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts2/users/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取脚本类型描述
     * @returns ScriptTypeGetOut Successful Response
     * @throws ApiError
     */
    public static getScriptTypesApiScriptTypesGetPost(): CancelablePromise<ScriptTypeGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/script-types/get',
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
     * 获取电源标志
     * @returns PowerOut Successful Response
     * @throws ApiError
     */
    public static getPowerApiDispatchGetPowerPost(): CancelablePromise<PowerOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/dispatch/get/power',
        });
    }
    /**
     * 设置电源标志
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setPowerApiDispatchSetPowerPost(
        requestBody: PowerIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/dispatch/set/power',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 取消电源任务
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static cancelPowerTaskApiDispatchCancelPowerPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/dispatch/cancel/power',
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
     * 查询工具配置
     * 获取工具设置
     * @returns ToolsGetOut Successful Response
     * @throws ApiError
     */
    public static getToolsApiToolsGetPost(): CancelablePromise<ToolsGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/get',
        });
    }
    /**
     * 更新工具配置
     * 更新工具配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateToolsApiToolsUpdatePost(
        requestBody: ToolsUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 手动触发游戏社区签到
     * 手动触发游戏社区签到
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static manualGameSignApiToolsSignPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign',
        });
    }
    /**
     * 获取所有游戏签到账号组
     * 获取所有游戏签到账号组
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
     * 添加游戏签到账号组
     * 添加游戏签到账号组
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
     * 获取游戏签到账号组详情
     * 获取游戏签到账号组详情
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
     * 更新游戏签到账号组配置
     * 更新游戏签到账号组配置
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
     * 删除游戏签到账号组
     * 删除游戏签到账号组
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
     * 调整游戏签到账号组顺序
     * 调整游戏签到账号组顺序
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
    /**
     * 测试通知
     * 测试通知
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static testNotifyApiSettingTestNotifyPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/test_notify',
        });
    }
    /**
     * 查询 webhook 配置
     * @param requestBody
     * @returns WebhookGetOut Successful Response
     * @throws ApiError
     */
    public static getWebhookApiSettingWebhookGetPost(
        requestBody: WebhookGetIn,
    ): CancelablePromise<WebhookGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加webhook项
     * @returns WebhookCreateOut Successful Response
     * @throws ApiError
     */
    public static addWebhookApiSettingWebhookAddPost(): CancelablePromise<WebhookCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/add',
        });
    }
    /**
     * 更新webhook项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateWebhookApiSettingWebhookUpdatePost(
        requestBody: WebhookUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/update',
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
    /**
     * 重新排序webhook项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderWebhookApiSettingWebhookOrderPost(
        requestBody: WebhookReorderIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 测试Webhook配置
     * 测试自定义Webhook
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static testWebhookApiSettingWebhookTestPost(
        requestBody: WebhookTestIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/test',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 检查更新
     * @param requestBody
     * @returns UpdateCheckOut Successful Response
     * @throws ApiError
     */
    public static checkUpdateApiUpdateCheckPost(
        requestBody: UpdateCheckIn,
    ): CancelablePromise<UpdateCheckOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/update/check',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 下载更新
     * @param version
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static downloadUpdateApiUpdateDownloadPost(
        version?: (string | null),
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/update/download',
            query: {
                'version': version,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 取消下载更新
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static cancelUpdateDownloadApiUpdateCancelDownloadPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/update/cancel-download',
        });
    }
    /**
     * 切换下载源到 CNB
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static switchUpdateDownloadToCnbApiUpdateSwitchToCnbPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/update/switch-to-cnb',
        });
    }
    /**
     * 安装更新
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static installUpdateApiUpdateInstallPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/update/install',
        });
    }
    /**
     * 获取主应用背景配置
     * @returns PluginFrontendBackgroundOut Successful Response
     * @throws ApiError
     */
    public static getFrontendBackgroundApiPluginsFrontendBackgroundGet(): CancelablePromise<PluginFrontendBackgroundOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/plugins/frontend/background',
        });
    }
    /**
     * 获取主应用背景图片
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getFrontendBackgroundImageApiPluginsFrontendBackgroundImageGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/plugins/frontend/background/image',
        });
    }
    /**
     * 获取插件前端扩展静态资源
     * @param pluginId
     * @param assetPath
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getPluginFrontendAssetApiPluginsAssetsPluginIdAssetPathGet(
        pluginId: string,
        assetPath: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/plugins/assets/{plugin_id}/{asset_path}',
            path: {
                'plugin_id': pluginId,
                'asset_path': assetPath,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取插件实例配置
     * @returns PluginsGetOut Successful Response
     * @throws ApiError
     */
    public static getPluginsApiPluginsGetPost(): CancelablePromise<PluginsGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugins/get',
        });
    }
    /**
     * 重载插件实例
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reloadPluginsApiPluginsReloadPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugins/reload',
        });
    }
    /**
     * 重载单个插件实例
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reloadPluginInstanceApiPluginsReloadInstancePost(
        requestBody: PluginReloadInstanceIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugins/reload_instance',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 按插件名重载所有实例
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reloadPluginByNameApiPluginsReloadPluginPost(
        requestBody: PluginReloadPluginIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugins/reload_plugin',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 下载安装插件包
     * 下载安装指定插件包。
     *
     * Args:
     * data (PluginPackageIn): 包名参数。
     *
     * Returns:
     * OutBase: 统一响应对象。
     *
     * Raises:
     * 无。接口内部会捕获异常并转换为统一错误响应。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static installPluginPackageApiPluginsInstallPackagePost(
        requestBody: PluginPackageIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugins/install_package',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 卸载插件包
     * 卸载指定插件包。
     *
     * Args:
     * data (PluginPackageIn): 包名参数。
     *
     * Returns:
     * OutBase: 统一响应对象。
     *
     * Raises:
     * 无。接口内部会捕获异常并转换为统一错误响应。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static uninstallPluginPackageApiPluginsUninstallPackagePost(
        requestBody: PluginPackageIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugins/uninstall_package',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 新增插件实例
     * @param requestBody
     * @returns PluginAddOut Successful Response
     * @throws ApiError
     */
    public static addPluginInstanceApiPluginsAddPost(
        requestBody: PluginAddIn,
    ): CancelablePromise<PluginAddOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugins/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新插件实例
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updatePluginInstanceApiPluginsUpdatePost(
        requestBody: PluginUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugins/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除插件实例
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deletePluginInstanceApiPluginsDeletePost(
        requestBody: PluginDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugins/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询游戏中心配置
     * @param requestBody
     * @returns GameGetOut Successful Response
     * @throws ApiError
     */
    public static getGameApiGameCenterGetPost(
        requestBody: GameGetIn,
    ): CancelablePromise<GameGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 添加游戏项
     * @param requestBody
     * @returns GameCreateOut Successful Response
     * @throws ApiError
     */
    public static addGameApiGameCenterAddPost(
        requestBody?: GameAddIn,
    ): CancelablePromise<GameCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新游戏项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static updateGameApiGameCenterUpdatePost(
        requestBody: GameUpdateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除游戏项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static deleteGameApiGameCenterDeletePost(
        requestBody: GameDeleteIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 重新排序游戏项
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static reorderGameApiGameCenterOrderPost(
        requestBody: GameReorderIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取内置游戏预设
     * @returns GamePresetsOut Successful Response
     * @throws ApiError
     */
    public static getPresetsApiGameCenterPresetsPost(): CancelablePromise<GamePresetsOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/presets',
        });
    }
    /**
     * 检查游戏更新
     * @param requestBody
     * @returns GameCheckOut Successful Response
     * @throws ApiError
     */
    public static checkGameApiGameCenterCheckPost(
        requestBody: GameOperateIn,
    ): CancelablePromise<GameCheckOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/check',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 安装或更新游戏 (后台任务)
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static installGameApiGameCenterInstallPost(
        requestBody: GameOperateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/install',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 取消安装/更新任务
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static cancelGameApiGameCenterCancelPost(
        requestBody: GameOperateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/cancel',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 启动游戏
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static launchGameApiGameCenterLaunchPost(
        requestBody: GameOperateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/launch',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 打开官方启动器 (鹰角回退)
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static openOfficialLauncherApiGameCenterOpenOfficialLauncherPost(
        requestBody: GameOperateIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/open_official_launcher',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 手动安装本地 APK (ADB 游戏)
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static installLocalApkApiGameCenterInstallLocalApkPost(
        requestBody: GameInstallLocalApkIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/install_local_apk',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询任务状态 (轮询兜底)
     * @param requestBody
     * @returns GameTaskStatusOut Successful Response
     * @throws ApiError
     */
    public static taskStatusApiGameCenterTaskStatusPost(
        requestBody: GameOperateIn,
    ): CancelablePromise<GameTaskStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/game_center/task_status',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 创建二维码
     * @returns QrCreateOut Successful Response
     * @throws ApiError
     */
    public static qrCreateApiToolsSignMiyousheQrCreatePost(): CancelablePromise<QrCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/miyoushe/qr/create',
        });
    }
    /**
     * 轮询扫码状态
     * 轮询状态，确认后 cookies 直接从响应头获取
     * @param requestBody
     * @returns QrCheckOut Successful Response
     * @throws ApiError
     */
    public static qrCheckApiToolsSignMiyousheQrCheckPost(
        requestBody: QrCheckIn,
    ): CancelablePromise<QrCheckOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/miyoushe/qr/check',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存 cookie 到账号配置
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static qrSaveApiToolsSignMiyousheQrSavePost(
        requestBody: QrSaveIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/miyoushe/qr/save',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
