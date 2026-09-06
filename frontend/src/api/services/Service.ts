/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BackendHealthOut } from '../models/BackendHealthOut';
import type { BetterGICustomGroupsOut } from '../models/BetterGICustomGroupsOut';
import type { BetterGIOneDragonSettingsIn } from '../models/BetterGIOneDragonSettingsIn';
import type { BetterGIOneDragonSettingsOut } from '../models/BetterGIOneDragonSettingsOut';
import type { BetterGIPathingTreeOut } from '../models/BetterGIPathingTreeOut';
import type { BetterGIScriptDirsOut } from '../models/BetterGIScriptDirsOut';
import type { Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post } from '../models/Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post';
import type { Body_update_oknte_config_api_scripts_oknte_configs_update_post } from '../models/Body_update_oknte_config_api_scripts_oknte_configs_update_post';
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
import type { GameSignAccountCreateOut } from '../models/GameSignAccountCreateOut';
import type { GameSignAccountDeleteIn } from '../models/GameSignAccountDeleteIn';
import type { GameSignAccountGetIn } from '../models/GameSignAccountGetIn';
import type { GameSignAccountReorderIn } from '../models/GameSignAccountReorderIn';
import type { GameSignAccountsListOut } from '../models/GameSignAccountsListOut';
import type { GameSignAccountUpdateIn } from '../models/GameSignAccountUpdateIn';
import type { GetStageIn } from '../models/GetStageIn';
import type { HistoryDataGetIn } from '../models/HistoryDataGetIn';
import type { HistoryDataGetOut } from '../models/HistoryDataGetOut';
import type { HistorySearchIn } from '../models/HistorySearchIn';
import type { HistorySearchOut } from '../models/HistorySearchOut';
import type { HSRCapabilitiesOut } from '../models/HSRCapabilitiesOut';
import type { HSRDirectConfigImportIn } from '../models/HSRDirectConfigImportIn';
import type { HSRDirectConfigImportOut } from '../models/HSRDirectConfigImportOut';
import type { HSRManagedConfigOut } from '../models/HSRManagedConfigOut';
import type { HSRSRAProfilesOut } from '../models/HSRSRAProfilesOut';
import type { HSRStageOptionsOut } from '../models/HSRStageOptionsOut';
import type { InfoOut } from '../models/InfoOut';
import type { MaaEndOptionsOut } from '../models/MaaEndOptionsOut';
import type { MaaFWAgentEnvPrepareIn } from '../models/MaaFWAgentEnvPrepareIn';
import type { MaaFWAgentEnvPrepareOut } from '../models/MaaFWAgentEnvPrepareOut';
import type { MaaFWInterfacePreviewIn } from '../models/MaaFWInterfacePreviewIn';
import type { MaaFWInterfacePreviewOut } from '../models/MaaFWInterfacePreviewOut';
import type { MaaFWProjectUpdateIn } from '../models/MaaFWProjectUpdateIn';
import type { MaaFWProjectUpdateOut } from '../models/MaaFWProjectUpdateOut';
import type { NoticeOut } from '../models/NoticeOut';
import type { OutBase } from '../models/OutBase';
import type { PatternDebugIn } from '../models/PatternDebugIn';
import type { PatternDebugOut } from '../models/PatternDebugOut';
import type { PlanComboxIn } from '../models/PlanComboxIn';
import type { PlanCreateIn } from '../models/PlanCreateIn';
import type { PlanCreateOut } from '../models/PlanCreateOut';
import type { PlanDeleteIn } from '../models/PlanDeleteIn';
import type { PlanGetIn } from '../models/PlanGetIn';
import type { PlanGetOut } from '../models/PlanGetOut';
import type { PlanReorderIn } from '../models/PlanReorderIn';
import type { PlanUpdateIn } from '../models/PlanUpdateIn';
import type { PowerCountdownSnapshot } from '../models/PowerCountdownSnapshot';
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
import type { ScriptReorderIn } from '../models/ScriptReorderIn';
import type { ScriptUpdateIn } from '../models/ScriptUpdateIn';
import type { ScriptUploadIn } from '../models/ScriptUploadIn';
import type { ScriptUrlIn } from '../models/ScriptUrlIn';
import type { SettingGetOut } from '../models/SettingGetOut';
import type { SettingUpdateIn } from '../models/SettingUpdateIn';
import type { SklandLoginIn } from '../models/SklandLoginIn';
import type { TaskCreateIn } from '../models/TaskCreateIn';
import type { TaskCreateOut } from '../models/TaskCreateOut';
import type { TaskRuntimeSnapshot } from '../models/TaskRuntimeSnapshot';
import type { TaygedoLoginIn } from '../models/TaygedoLoginIn';
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
import type { UpdateDownloadSnapshot } from '../models/UpdateDownloadSnapshot';
import type { UserCreateOut } from '../models/UserCreateOut';
import type { UserDeleteIn } from '../models/UserDeleteIn';
import type { UserGetIn } from '../models/UserGetIn';
import type { UserGetOut } from '../models/UserGetOut';
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
     * 获取后端就绪状态
     * 返回核心 API 与后台初始化状态，供 AUTO-MAS-Runtime 等外部监督器判定就绪与身份。
     *
     * version/commit 受监督且监督器注入了期望值时原样回显，否则分别回退到本地版本号
     * 与空字符串；commit 不通过 Git 推断，只能来自监督器注入。
     * @returns BackendHealthOut Successful Response
     * @throws ApiError
     */
    public static getHealthApiCoreHealthGet(): CancelablePromise<BackendHealthOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/core/health',
        });
    }
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
     * 关闭后端程序：启动清理流程，完成后经主 WS 发送 backend.shutdown.ready
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
     * @param requestBody
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getPlanComboxApiInfoComboxPlanPost(
        requestBody: PlanComboxIn,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/combox/plan',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
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
     * 获取 MaaEnd 动态选项
     * @param requestBody
     * @returns MaaEndOptionsOut Successful Response
     * @throws ApiError
     */
    public static getMaaendOptionsApiScriptsMaaendOptionsPost(
        requestBody: ScriptDeleteIn,
    ): CancelablePromise<MaaEndOptionsOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maaend/options',
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
     * MAA 库存保持物品可选项
     * @param requestBody
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getMaaDepotItemsApiScriptsMaaDepotItemsPost(
        requestBody: ScriptDeleteIn,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maa/depot/items',
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
     * 预览 MFW interface
     * 读取 MaaFW 项目 interface，并返回 controller/resource/task 摘要。
     * @param requestBody
     * @returns MaaFWInterfacePreviewOut Successful Response
     * @throws ApiError
     */
    public static previewMaafwInterfaceApiScriptsMaafwPreviewPost(
        requestBody: MaaFWInterfacePreviewIn,
    ): CancelablePromise<MaaFWInterfacePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 检查或执行 MFW 项目更新
     * 按脚本 ``Update.*`` 配置检查或应用 MaaFW 项目目录更新。
     *
     * ``action=check`` 只读取 interface 版本与更新源元数据，返回是否有新版本；
     * ``action=apply`` 触发下载并原地应用更新包。失败时返回明确 ``message``。
     * @param requestBody
     * @returns MaaFWProjectUpdateOut Successful Response
     * @throws ApiError
     */
    public static updateMaafwProjectApiScriptsMaafwUpdatePost(
        requestBody: MaaFWProjectUpdateIn,
    ): CancelablePromise<MaaFWProjectUpdateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 预备 MFW 运行环境
     * 按项目 interface 预备 Runner 运行时与各 agent 的 Python 环境。
     *
     * 在项目引导里读到 interface 之后调用，把首次运行才会付出的下载与建环境
     * 成本提前到配置阶段。与 ``/maafw/update`` 一样是同步端点：整个准备过程
     * 在请求内完成，首次冷启动可能耗时数分钟。
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
     * 获取 HSR 体力副本动态选项
     * 返回 M7A/SRA 原生副本字段。
     *
     * ``userId`` 仅用于校验用户归属；``slot`` 是兼容参数，动态选项当前
     * 按引擎统一返回，不按 slot 生成不同结果。
     * @param scriptId
     * @param engine
     * @param userId
     * @param slot
     * @returns HSRStageOptionsOut Successful Response
     * @throws ApiError
     */
    public static getHsrStageOptionsApiApiScriptsHsrStageOptionsGet(
        scriptId?: (string | null),
        engine: 'M7A' | 'SRA' = 'M7A',
        userId?: (string | null),
        slot: 'main' | 'eow' = 'main',
    ): CancelablePromise<HSRStageOptionsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/stage-options',
            query: {
                'scriptId': scriptId,
                'engine': engine,
                'userId': userId,
                'slot': slot,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
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
    /**
     * 获取内置 HSR 能力快照
     * 返回内置 HSR 的能力快照，不暴露原生编辑器会话。
     * @param scriptId
     * @returns HSRCapabilitiesOut Successful Response
     * @throws ApiError
     */
    public static getHsrCapabilitiesApiApiScriptsHsrCapabilitiesGet(
        scriptId?: (string | null),
    ): CancelablePromise<HSRCapabilitiesOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/capabilities',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 HSR 托管配置字段
     * 返回原生动态托管字段；用户 ID 只负责归属校验。
     * @param scriptId
     * @param userId
     * @returns HSRManagedConfigOut Successful Response
     * @throws ApiError
     */
    public static getHsrManagedConfigApiApiScriptsHsrManagedConfigGet(
        scriptId?: (string | null),
        userId?: (string | null),
    ): CancelablePromise<HSRManagedConfigOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/managed-config',
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
     * 获取 HSR 可选的 SRA 配置档案
     * 列出 ``%APPDATA%/SRA/configs`` 下的配置档案，并标出脚本当前生效的那份。
     * @param scriptId
     * @returns HSRSRAProfilesOut Successful Response
     * @throws ApiError
     */
    public static getHsrSraProfilesApiApiScriptsHsrSraProfilesGet(
        scriptId?: (string | null),
    ): CancelablePromise<HSRSRAProfilesOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/hsr/sra-profiles',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 导入 HSR 原生配置快照
     * @param requestBody
     * @returns HSRDirectConfigImportOut Successful Response
     * @throws ApiError
     */
    public static importHsrDirectConfigApiApiScriptsHsrDirectConfigImportPost(
        requestBody: HSRDirectConfigImportIn,
    ): CancelablePromise<HSRDirectConfigImportOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/hsr/direct-config/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 清除 HSR 用户的直控配置快照
     * 清掉该用户导入的快照，直控回到直接使用脚本当前原生配置。
     * @param requestBody
     * @returns HSRDirectConfigImportOut Successful Response
     * @throws ApiError
     */
    public static clearHsrDirectConfigApiApiScriptsHsrDirectConfigClearPost(
        requestBody: HSRDirectConfigImportIn,
    ): CancelablePromise<HSRDirectConfigImportOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/hsr/direct-config/clear',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 OK-NTE 配置文件列表及 schema
     * 获取 OK-NTE 配置文件列表及 schema 定义。
     * 读写用户配置目录（data/{script_id}/{user_id}/ConfigFile/），
     * 若为空则自动从 ok-nte configs 目录初始化默认配置。
     *
     * Args:
     * script_id: OK-NTE 脚本 ID
     * user_id: 用户 ID
     *
     * Returns:
     * dict: 包含配置文件列表和 schema 的响应
     * @param scriptId
     * @param userId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getOknteConfigsListApiScriptsOknteConfigsListPost(
        scriptId: string,
        userId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/oknte/configs/list',
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
     * 更新 OK-NTE 配置文件
     * 更新 OK-NTE 配置文件
     *
     * Args:
     * script_id: OK-NTE 脚本 ID
     * user_id: 用户 ID
     * filename: 配置文件名（如 DailyTask.json）
     * data: 要更新的配置数据
     *
     * Returns:
     * dict: 操作结果
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static updateOknteConfigApiScriptsOknteConfigsUpdatePost(
        requestBody: Body_update_oknte_config_api_scripts_oknte_configs_update_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/oknte/configs/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量更新 OK-NTE 配置文件
     * 批量更新 OK-NTE 配置文件
     *
     * Args:
     * script_id: OK-NTE 脚本 ID
     * user_id: 用户 ID
     * configs: { filename: data } 格式的配置数据
     *
     * Returns:
     * dict: 操作结果
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static batchUpdateOknteConfigsApiScriptsOknteConfigsBatchUpdatePost(
        requestBody: Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/oknte/configs/batch-update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 读取 MFW 项目内的图片资源
     * 把 MFW 项目目录内的图片按需读给前端。
     *
     * 任务说明（interface 的 ``doc`` / ``description``）是 markdown，里面的图片写的是
     * **项目内相对路径**，浏览器没法直接读本地文件，必须由后端转一手。
     *
     * 前端侧对应 ``buildMaaFWAssetUrl``：它已经拦掉了绝对路径、UNC、上跳与远程 URL，
     * 但那只是省一次往返，安全边界在这里 —— 请求可以绕过前端直接打过来。
     * @param root MFW 项目根目录
     * @param path 项目根目录内的相对图片路径
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
     * 枚举卸载表并解析主管理器路径（不依赖 ADB 设备枚举）。
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
     * 获取运行中任务初始快照
     * 返回当前运行任务；WS 只承载后续状态、日志与完成事件。
     * @returns TaskRuntimeSnapshot Successful Response
     * @throws ApiError
     */
    public static getTaskRuntimeSnapshotApiDispatchRuntimeSnapshotGet(): CancelablePromise<TaskRuntimeSnapshot> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/dispatch/runtime-snapshot',
        });
    }
    /**
     * 获取电源倒计时初始快照
     * 返回当前倒计时；WS 只承载后续逐秒更新与取消事件。
     * @returns PowerCountdownSnapshot Successful Response
     * @throws ApiError
     */
    public static getPowerCountdownSnapshotApiDispatchPowerCountdownSnapshotGet(): CancelablePromise<PowerCountdownSnapshot> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/dispatch/power/countdown-snapshot',
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
    /**
     * 导出数据备份
     * 导出数据、配置与历史记录。
     * @returns any Successful Response
     * @throws ApiError
     */
    public static backupDataApiSettingBackupGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/setting/backup',
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
     * 调试日志模式
     * 调试单条日志模式配置，返回逐行/逐窗口匹配结果
     *
     * 前端调试弹窗调用此接口，由后端统一执行模式匹配，
     * 确保调试结果与实际推送日志采集逻辑完全一致。
     * @param requestBody
     * @returns PatternDebugOut Successful Response
     * @throws ApiError
     */
    public static debugPatternApiApiSettingDebugPatternPost(
        requestBody: PatternDebugIn,
    ): CancelablePromise<PatternDebugOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/debug_pattern',
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
     * 获取更新下载初始快照
     * 返回当前下载权威状态；WS 只承载后续进度与终态事件。
     * @returns UpdateDownloadSnapshot Successful Response
     * @throws ApiError
     */
    public static getUpdateDownloadStatusApiUpdateDownloadStatusGet(): CancelablePromise<UpdateDownloadSnapshot> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/update/download/status',
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
     * 轮询状态，确认后返回从 Passport 响应提取的 cookies。
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
