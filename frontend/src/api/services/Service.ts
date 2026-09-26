/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BackendHealthOut } from '../models/BackendHealthOut';
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
import type { BlueArchiveActivityIn } from '../models/BlueArchiveActivityIn';
import type { BlueArchiveActivityStatusOut } from '../models/BlueArchiveActivityStatusOut';
import type { Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post } from '../models/Body_batch_update_oknte_configs_api_scripts_oknte_configs_batch_update_post';
import type { Body_get_maa_cultivate_operators_api_scripts_maa_cultivate_operators_post } from '../models/Body_get_maa_cultivate_operators_api_scripts_maa_cultivate_operators_post';
import type { Body_get_maa_depot_inventory_api_scripts_maa_depot_inventory_post } from '../models/Body_get_maa_depot_inventory_api_scripts_maa_depot_inventory_post';
import type { Body_get_maa_depot_stage_candidates_api_scripts_maa_depot_stage_candidates_post } from '../models/Body_get_maa_depot_stage_candidates_api_scripts_maa_depot_stage_candidates_post';
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { CommunityActivityOut } from '../models/CommunityActivityOut';
import type { CommunityActivityQueryIn } from '../models/CommunityActivityQueryIn';
import type { ConfigBackupEnsureIn } from '../models/ConfigBackupEnsureIn';
import type { ConfigBackupEnsureOut } from '../models/ConfigBackupEnsureOut';
import type { ConfigBackupFileOut } from '../models/ConfigBackupFileOut';
import type { ConfigBackupListOut } from '../models/ConfigBackupListOut';
import type { ConfigBackupPreviewOut } from '../models/ConfigBackupPreviewOut';
import type { ConfigBackupRestoreIn } from '../models/ConfigBackupRestoreIn';
import type { ConfigBackupRestoreOut } from '../models/ConfigBackupRestoreOut';
import type { CultivatePreviewIn } from '../models/CultivatePreviewIn';
import type { CultivatePreviewOut } from '../models/CultivatePreviewOut';
import type { DispatchIn } from '../models/DispatchIn';
import type { EmulatorCreateOut } from '../models/EmulatorCreateOut';
import type { EmulatorDeleteIn } from '../models/EmulatorDeleteIn';
import type { EmulatorGetIn } from '../models/EmulatorGetIn';
import type { EmulatorGetOut } from '../models/EmulatorGetOut';
import type { EmulatorOperateIn } from '../models/EmulatorOperateIn';
import type { EmulatorSearchOut } from '../models/EmulatorSearchOut';
import type { EmulatorStatusOut } from '../models/EmulatorStatusOut';
import type { EmulatorUpdateIn } from '../models/EmulatorUpdateIn';
import type { GameSignAccountCreateOut } from '../models/GameSignAccountCreateOut';
import type { GameSignAccountDeleteIn } from '../models/GameSignAccountDeleteIn';
import type { GameSignAccountReorderIn } from '../models/GameSignAccountReorderIn';
import type { GameSignAccountsListOut } from '../models/GameSignAccountsListOut';
import type { GameSignAccountUpdateIn } from '../models/GameSignAccountUpdateIn';
import type { GetStageIn } from '../models/GetStageIn';
import type { HistoryDataGetIn } from '../models/HistoryDataGetIn';
import type { HistoryDataGetOut } from '../models/HistoryDataGetOut';
import type { HistorySearchIn } from '../models/HistorySearchIn';
import type { HistorySearchOut } from '../models/HistorySearchOut';
import type { HSRCapabilitiesOut } from '../models/HSRCapabilitiesOut';
import type { HSRCloudLoginIn } from '../models/HSRCloudLoginIn';
import type { HSRCloudLoginOut } from '../models/HSRCloudLoginOut';
import type { HSRManagedConfigOut } from '../models/HSRManagedConfigOut';
import type { HSRSRAProfilesOut } from '../models/HSRSRAProfilesOut';
import type { HSRStageOptionsOut } from '../models/HSRStageOptionsOut';
import type { HSRUpdateIn } from '../models/HSRUpdateIn';
import type { HSRUpdateOut } from '../models/HSRUpdateOut';
import type { InfoOut } from '../models/InfoOut';
import type { MaaCultivateOperatorsOut } from '../models/MaaCultivateOperatorsOut';
import type { MaaDepotInventoryOut } from '../models/MaaDepotInventoryOut';
import type { MaaEndOptionsOut } from '../models/MaaEndOptionsOut';
import type { MaaFWAgentEnvPrepareIn } from '../models/MaaFWAgentEnvPrepareIn';
import type { MaaFWAgentEnvPrepareOut } from '../models/MaaFWAgentEnvPrepareOut';
import type { MaaFWEmbeddedCloneIn } from '../models/MaaFWEmbeddedCloneIn';
import type { MaaFWEmbeddedIn } from '../models/MaaFWEmbeddedIn';
import type { MaaFWEmbeddedReimportIn } from '../models/MaaFWEmbeddedReimportIn';
import type { MaaFWEmbeddedSourcesIn } from '../models/MaaFWEmbeddedSourcesIn';
import type { MaaFWEmbeddedSourcesOut } from '../models/MaaFWEmbeddedSourcesOut';
import type { MaaFWEmbeddedStatusOut } from '../models/MaaFWEmbeddedStatusOut';
import type { MaaFWGamePackageIn } from '../models/MaaFWGamePackageIn';
import type { MaaFWGamePackageOut } from '../models/MaaFWGamePackageOut';
import type { MaaFWInterfacePreviewIn } from '../models/MaaFWInterfacePreviewIn';
import type { MaaFWInterfacePreviewOut } from '../models/MaaFWInterfacePreviewOut';
import type { MaaFWProjectUpdateIn } from '../models/MaaFWProjectUpdateIn';
import type { MaaFWProjectUpdateOut } from '../models/MaaFWProjectUpdateOut';
import type { MaaFWShellInstanceImportIn } from '../models/MaaFWShellInstanceImportIn';
import type { MaaFWShellInstanceImportOut } from '../models/MaaFWShellInstanceImportOut';
import type { MaaFWShellInstancesIn } from '../models/MaaFWShellInstancesIn';
import type { MaaFWShellInstancesOut } from '../models/MaaFWShellInstancesOut';
import type { NoticeOut } from '../models/NoticeOut';
import type { NotifyChannelsOut } from '../models/NotifyChannelsOut';
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
import type { QueueSetInBase } from '../models/QueueSetInBase';
import type { QueueUpdateIn } from '../models/QueueUpdateIn';
import type { ScriptConfigImportIn } from '../models/ScriptConfigImportIn';
import type { ScriptCreateIn } from '../models/ScriptCreateIn';
import type { ScriptCreateOut } from '../models/ScriptCreateOut';
import type { ScriptDeleteIn } from '../models/ScriptDeleteIn';
import type { ScriptGetIn } from '../models/ScriptGetIn';
import type { ScriptGetOut } from '../models/ScriptGetOut';
import type { ScriptReorderIn } from '../models/ScriptReorderIn';
import type { ScriptUpdateIn } from '../models/ScriptUpdateIn';
import type { ScriptUploadIn } from '../models/ScriptUploadIn';
import type { ScriptUrlIn } from '../models/ScriptUrlIn';
import type { SettingGetOut } from '../models/SettingGetOut';
import type { SettingUpdateIn } from '../models/SettingUpdateIn';
import type { SklandQrCheckIn } from '../models/SklandQrCheckIn';
import type { SklandQrCheckOut } from '../models/SklandQrCheckOut';
import type { SklandQrCreateOut } from '../models/SklandQrCreateOut';
import type { SklandQrSaveIn } from '../models/SklandQrSaveIn';
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
import type { UserConfigDirIn } from '../models/UserConfigDirIn';
import type { UserConfigDirOut } from '../models/UserConfigDirOut';
import type { UserCreateOut } from '../models/UserCreateOut';
import type { UserDeleteIn } from '../models/UserDeleteIn';
import type { UserGetIn } from '../models/UserGetIn';
import type { UserGetOut } from '../models/UserGetOut';
import type { UserInBase } from '../models/UserInBase';
import type { UserInfrastPlanComboxOut } from '../models/UserInfrastPlanComboxOut';
import type { UserInfrastPlanSelectIn } from '../models/UserInfrastPlanSelectIn';
import type { UserInfrastPlanSelectOut } from '../models/UserInfrastPlanSelectOut';
import type { UserReorderIn } from '../models/UserReorderIn';
import type { UserSetIn } from '../models/UserSetIn';
import type { UserUpdateIn } from '../models/UserUpdateIn';
import type { VersionOut } from '../models/VersionOut';
import type { VirtualDisplayCheckOut } from '../models/VirtualDisplayCheckOut';
import type { VirtualDisplayDetachOut } from '../models/VirtualDisplayDetachOut';
import type { WebhookCreateOut } from '../models/WebhookCreateOut';
import type { WebhookDeleteIn } from '../models/WebhookDeleteIn';
import type { WebhookGetIn } from '../models/WebhookGetIn';
import type { WebhookGetOut } from '../models/WebhookGetOut';
import type { WebhookInBase } from '../models/WebhookInBase';
import type { WebhookTestIn } from '../models/WebhookTestIn';
import type { WebhookUpdateIn } from '../models/WebhookUpdateIn';
import type { WebSocketMetaOut } from '../models/WebSocketMetaOut';
import type { ZzzOdAppConfigOut } from '../models/ZzzOdAppConfigOut';
import type { ZzzOdAppConfigSaveIn } from '../models/ZzzOdAppConfigSaveIn';
import type { ZzzOdCatalogOut } from '../models/ZzzOdCatalogOut';
import type { ZzzOdImportIn } from '../models/ZzzOdImportIn';
import type { ZzzOdImportOut } from '../models/ZzzOdImportOut';
import type { ZzzOdInstanceActiveIn } from '../models/ZzzOdInstanceActiveIn';
import type { ZzzOdInstanceAddIn } from '../models/ZzzOdInstanceAddIn';
import type { ZzzOdInstanceDeleteIn } from '../models/ZzzOdInstanceDeleteIn';
import type { ZzzOdInstanceFlagIn } from '../models/ZzzOdInstanceFlagIn';
import type { ZzzOdInstanceForceLoginIn } from '../models/ZzzOdInstanceForceLoginIn';
import type { ZzzOdInstanceRenameIn } from '../models/ZzzOdInstanceRenameIn';
import type { ZzzOdInstanceRunModeIn } from '../models/ZzzOdInstanceRunModeIn';
import type { ZzzOdInstancesOut } from '../models/ZzzOdInstancesOut';
import type { ZzzOdLauncherOut } from '../models/ZzzOdLauncherOut';
import type { ZzzOdNativeConfigIn } from '../models/ZzzOdNativeConfigIn';
import type { ZzzOdNativeConfigOut } from '../models/ZzzOdNativeConfigOut';
import type { ZzzOdRecycleClearIn } from '../models/ZzzOdRecycleClearIn';
import type { ZzzOdRecycleClearOut } from '../models/ZzzOdRecycleClearOut';
import type { ZzzOdRecycleOut } from '../models/ZzzOdRecycleOut';
import type { ZzzOdRecycleRestoreIn } from '../models/ZzzOdRecycleRestoreIn';
import type { ZzzOdSlotCleanIn } from '../models/ZzzOdSlotCleanIn';
import type { ZzzOdSlotCleanOut } from '../models/ZzzOdSlotCleanOut';
import type { ZzzOdSlotsOut } from '../models/ZzzOdSlotsOut';
import type { ZzzOdTaskOptionsOut } from '../models/ZzzOdTaskOptionsOut';
import type { ZzzOdTeamsOut } from '../models/ZzzOdTeamsOut';
import type { ZzzOdTeamsSaveIn } from '../models/ZzzOdTeamsSaveIn';
import type { ZzzOdTeamsSaveOut } from '../models/ZzzOdTeamsSaveOut';
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
     * 获取碧蓝档案活动数据（Kivo 中转）
     * 按服务器取回碧蓝档案的活动时间轴。
     *
     * 这里只做转发：把 Kivo 的响应原样交给前端，筛选与格式转换都由前端完成。
     * 之所以要绕一道后端，是因为 Kivo 的接口校验 Origin，浏览器直连必定 403。
     * @param requestBody
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static getBluearchiveActivityApiInfoBluearchiveActivityPost(
        requestBody: BlueArchiveActivityIn,
    ): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/bluearchive/activity',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取星塔旅人活动数据（StellaBase 中转）
     * 取回星塔旅人的活动排期。
     *
     * StellaBase 不放开跨域，浏览器直连拿不到数据，所以统一由后端中转——筛选与
     * 格式转换仍由前端完成，与碧蓝档案那条链路一致。取数失败返回错误信封，由卡片
     * 显示自己的失败态，不影响其它卡片。
     *
     * 顺带捎上国服官网的主推横幅（``official``）：StellaBase 的活动大图时有时无，
     * 官网那张 795×510 的官方主视觉正好当封面兜底；官网挂了不影响排期本身。
     * 其中与当前活动对得上号的那条会带 ``matched: true``，前端优先用它。
     *
     * Returns:
     * InfoOut: 站点原始响应，另加 ``official`` 横幅列表；取不到排期时返回
     * ``code=500`` 的错误信封。
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static getStellaActivityApiInfoStellaActivityPost(): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/info/stella/activity',
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
     * 获取用户配置目录
     * @param requestBody
     * @returns UserConfigDirOut Successful Response
     * @throws ApiError
     */
    public static getUserConfigDirApiScriptsUserConfigDirPost(
        requestBody: UserConfigDirIn,
    ): CancelablePromise<UserConfigDirOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/config-dir',
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
     * 设置基建班次
     * @param requestBody
     * @returns UserInfrastPlanSelectOut Successful Response
     * @throws ApiError
     */
    public static setInfrastPlanSelectApiScriptsUserInfrastructurePlanSelectPost(
        requestBody: UserInfrastPlanSelectIn,
    ): CancelablePromise<UserInfrastPlanSelectOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/infrastructure/plan-select',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取当前基建班次
     * @param requestBody
     * @returns UserInfrastPlanSelectOut Successful Response
     * @throws ApiError
     */
    public static getInfrastPlanSelectApiScriptsUserInfrastructurePlanSelectGetPost(
        requestBody: UserDeleteIn,
    ): CancelablePromise<UserInfrastPlanSelectOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/user/infrastructure/plan-select/get',
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
     * @returns UserInfrastPlanComboxOut Successful Response
     * @throws ApiError
     */
    public static getUserComboxInfrastructureApiScriptsUserComboxInfrastructurePost(
        requestBody: UserDeleteIn,
    ): CancelablePromise<UserInfrastPlanComboxOut> {
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
     * MAA 库存保持关卡候选（掉落指定材料，按单件期望理智升序，label 为 xx 理智/件）
     * @param requestBody
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getMaaDepotStageCandidatesApiScriptsMaaDepotStageCandidatesPost(
        requestBody: Body_get_maa_depot_stage_candidates_api_scripts_maa_depot_stage_candidates_post,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maa/depot/stage/candidates',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * MAA 仓库库存（当前用户档案；label=数量字符串，value=物品ID）
     * @param requestBody
     * @returns MaaDepotInventoryOut Successful Response
     * @throws ApiError
     */
    public static getMaaDepotInventoryApiScriptsMaaDepotInventoryPost(
        requestBody: Body_get_maa_depot_inventory_api_scripts_maa_depot_inventory_post,
    ): CancelablePromise<MaaDepotInventoryOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maa/depot/inventory',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 森空岛绑定角色列表（遍历已配置森空岛凭据的签到账号组，明日方舟）
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getMaaCultivateSklandBindingsApiScriptsMaaCultivateSklandBindingsPost(): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maa/cultivate/skland/bindings',
        });
    }
    /**
     * MAA 干员养成选择器目录（含技能/模组名称目录，稀有度降序）
     * @param requestBody
     * @returns MaaCultivateOperatorsOut Successful Response
     * @throws ApiError
     */
    public static getMaaCultivateOperatorsApiScriptsMaaCultivateOperatorsPost(
        requestBody: Body_get_maa_cultivate_operators_api_scripts_maa_cultivate_operators_post,
    ): CancelablePromise<MaaCultivateOperatorsOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maa/cultivate/operators',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * MAA 养成计划预览（纯计算不落库）
     * @param requestBody
     * @returns CultivatePreviewOut Successful Response
     * @throws ApiError
     */
    public static getMaaCultivatePreviewApiScriptsMaaCultivatePreviewPost(
        requestBody: CultivatePreviewIn,
    ): CancelablePromise<CultivatePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maa/cultivate/preview',
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
     * 查看 MFW 脚本的内嵌副本状态
     * @param requestBody
     * @returns MaaFWEmbeddedStatusOut Successful Response
     * @throws ApiError
     */
    public static getMaafwEmbeddedStatusApiScriptsMaafwEmbeddedStatusPost(
        requestBody: MaaFWEmbeddedIn,
    ): CancelablePromise<MaaFWEmbeddedStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/embedded/status',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 按来源目录导入（或重新导入）副本
     * 脚本页选目录就是走这里：第一次是导入，之后是换来源或按当前来源重导。
     *
     * 导入成功才把来源写进 Info.Path；失败时旧副本与旧来源都原样不动。
     * @param requestBody
     * @returns MaaFWEmbeddedStatusOut Successful Response
     * @throws ApiError
     */
    public static reimportMaafwEmbeddedApiScriptsMaafwEmbeddedReimportPost(
        requestBody: MaaFWEmbeddedReimportIn,
    ): CancelablePromise<MaaFWEmbeddedStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/embedded/reimport',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 列出可作为克隆来源的其它 MFW 脚本
     * 新建脚本对话框里「复用已有脚本的项目」的候选：有健康副本的 MFW / M9A 脚本。
     *
     * 新建时脚本还没建出来，所以不要求 ``scriptId``；传了就把它自己排除掉。
     * @param requestBody
     * @returns MaaFWEmbeddedSourcesOut Successful Response
     * @throws ApiError
     */
    public static listMaafwEmbeddedSourcesApiScriptsMaafwEmbeddedSourcesPost(
        requestBody?: MaaFWEmbeddedSourcesIn,
    ): CancelablePromise<MaaFWEmbeddedSourcesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/embedded/sources',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 从另一个 MFW 脚本的副本克隆，同一项目再建一个脚本
     * 同一个项目要开第二、第三个脚本（不同模拟器并行跑）时走这里，不用再选目录
     * 重新投影，来源目录已经删了也能建。
     *
     * 副本从源脚本的副本硬链接克隆（运行时、模型与其它副本共用，只多小文件），
     * ``Info.Path`` 与 ``Embedded.*`` 沿用源脚本的记录；类型随项目（M9A 项目 → M9A）。
     * 用户、任务队列与运行设置不带——那是「复制脚本」的事。
     * @param requestBody
     * @returns MaaFWEmbeddedStatusOut Successful Response
     * @throws ApiError
     */
    public static cloneMaafwEmbeddedApiScriptsMaafwEmbeddedClonePost(
        requestBody: MaaFWEmbeddedCloneIn,
    ): CancelablePromise<MaaFWEmbeddedStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/embedded/clone',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 列出项目目录里外壳（MFAAvalonia / MXU / MFW-PyQt6）保存的配置实例
     * 新建脚本引导最后一步用：外壳里配好的每份实例都可以导入成一个用户。只读外壳文件。
     * @param requestBody
     * @returns MaaFWShellInstancesOut Successful Response
     * @throws ApiError
     */
    public static listMaafwShellInstancesApiScriptsMaafwShellInstancesPost(
        requestBody: MaaFWShellInstancesIn,
    ): CancelablePromise<MaaFWShellInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/shell-instances',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 把选中的外壳配置实例导入成用户
     * 每个实例建一个用户：用户名取实例名，任务队列与任务选项一起导入。
     *
     * 逐个实例独立处理，失败原因与当前项目里对不上而跳过的任务 / 选项写在各项结果里。
     * @param requestBody
     * @returns MaaFWShellInstanceImportOut Successful Response
     * @throws ApiError
     */
    public static importMaafwShellInstancesApiScriptsMaafwShellInstancesImportPost(
        requestBody: MaaFWShellInstanceImportIn,
    ): CancelablePromise<MaaFWShellInstanceImportOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/shell-instances/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 按所选 resource 推断 MFW 项目的安卓游戏包名
     * 脚本编辑页读完 interface / 切换 resource 时调用，把推出来的包名直接填进表单。
     *
     * 只看 resource 的 pipeline，不带用户任务的 pipeline_override（编辑脚本时还没有
     * 运行计划）；推不出或多个候选都按原样返回，由前端决定不填。
     * @param requestBody
     * @returns MaaFWGamePackageOut Successful Response
     * @throws ApiError
     */
    public static resolveMaafwGamePackageApiScriptsMaafwGamePackagePost(
        requestBody: MaaFWGamePackageIn,
    ): CancelablePromise<MaaFWGamePackageOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maafw/game-package',
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
     *
     * 编辑页每打开一次就会调一次，所以先比一遍项目输入指纹：项目没更新过、上次
     * 准备的环境也还在盘上，就直接还回上次的结果，不再取锁起进程。用户手动重试
     * 时前端带 ``force``，跳过这层缓存。
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
     * 获取 BAAH 配置文件名列表
     * 返回 BAAH 配置目录下已有的配置文件名（不含 ``.json`` 后缀）。
     * @param scriptId
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getBaahConfigNamesApiApiScriptsBaahConfigNamesGet(
        scriptId: string,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/baah/config-names',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取碧蓝档案活动状态
     * 返回指定服正在进行的活动，没有则返回下一个未开始的活动。
     * @param lineType
     * @returns BlueArchiveActivityStatusOut Successful Response
     * @throws ApiError
     */
    public static getBaahActivityStatusApiApiScriptsBaahActivityStatusGet(
        lineType: 'JP' | 'Globle' | 'CN' = 'CN',
    ): CancelablePromise<BlueArchiveActivityStatusOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/baah/activity-status',
            query: {
                'lineType': lineType,
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
     * 获取 BetterGI 可用键鼠脚本（录制）列表
     * 返回 BetterGI 键鼠脚本（录制）候选。
     *
     * ``label`` 与 ``value`` 同为 {RootPath}/User/KeyMouseScript*.json 的文件名（即脚本名）。
     * 供一条龙「添加配置组」弹窗的「录制」标签页作为候选（贴录制标签）选择。
     * @param scriptId
     * @returns ComboBoxOut Successful Response
     * @throws ApiError
     */
    public static getBettergiKeyMouseScriptsApiApiScriptsBettergiKeyMouseScriptsGet(
        scriptId: string,
    ): CancelablePromise<ComboBoxOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/key-mouse-scripts',
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
    /**
     * 获取 BetterGI 一条龙设置项（右栏按任务分组展示）
     * 返回某用户一条龙配置的设置项（per-user 副本 → BGI 实配 → 内置模板的种子顺序）。
     *
     * 供右栏按任务分组渲染并回显该任务在 BGI 一条龙里的可设置字段。
     * ``groupName`` 为右栏当前编辑的内置组名，战斗 4 项 Plan 回显按其查映射，
     * 缺省/不匹配时跳过 Plan 回显。
     * @param scriptId
     * @param userId
     * @param configName
     * @param groupName
     * @returns BetterGIOneDragonSettingsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiOneDragonSettingsApiApiScriptsBettergiOneDragonSettingsGet(
        scriptId: string,
        userId: string,
        configName: string = '',
        groupName: string = '',
    ): CancelablePromise<BetterGIOneDragonSettingsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/one-dragon/settings',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'configName': configName,
                'groupName': groupName,
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
     * 设置一条龙 Plan 某步骤的启用状态（按实例名，支持 基名-后缀）
     * 按步骤名翻转 Plan 中某战斗实例的启用状态（同组多实例各自独立启停）。
     *
     * 步骤名由行实例 uid 决定（形如 ``自动秘境`` / ``自动秘境-3``），与前端展示用的
     * 「后名」解耦，改名不会丢设置。本接口只写 Plan（不改原生副本文件），但它是前端
     * 队列行的启停开关：运行时 build_combat_steps 按 step.enabled 决定是否纳入执行层，
     * 且 AutoProxy 会把 Plan 中配过实例的战斗组整体从原生副本剔除——因此 enabled=false
     * 的最终语义是「本次不跑」，而不是「退回原生一条龙跑」。
     *
     * 步骤不存在时（刚另存为/复制出来的新实例）先创建再设启用——否则开关只改前端、
     * 后端无步骤可写，刷新后回退。
     * @param scriptId
     * @param userId
     * @param name
     * @param enabled
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setOneDragonPlanStepEnabledApiScriptsBettergiOneDragonPlanStepEnabledPost(
        scriptId: string,
        userId: string,
        name: string,
        enabled: boolean = true,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/bettergi/one-dragon/plan/step-enabled',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'name': name,
                'enabled': enabled,
            },
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
     * @param groupName
     * @returns BetterGIGlobalDomainSettingsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiGlobalDomainSettingsApiApiScriptsBettergiGlobalDomainSettingsGet(
        scriptId: string,
        userId: string = '',
        groupName: string = '',
    ): CancelablePromise<BetterGIGlobalDomainSettingsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/global-domain/settings',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'groupName': groupName,
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
     * @param groupName
     * @returns BetterGIGlobalStygianSettingsOut Successful Response
     * @throws ApiError
     */
    public static getBettergiGlobalStygianSettingsApiApiScriptsBettergiGlobalStygianSettingsGet(
        scriptId: string,
        userId: string = '',
        groupName: string = '',
    ): CancelablePromise<BetterGIGlobalStygianSettingsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/bettergi/global-stygian/settings',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'groupName': groupName,
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
     * 保存 BetterGI 配置组 json 到 per-user 副本
     * 把右栏编辑后的配置组 json（项目顺序 + 各项目 jsScriptSettingsObject）写回
     * 该用户的 per-user 副本（``data/{script}/{user}/ScriptGroup/{name}.json``）。
     *
     * 「路径」类引用（名字含 ``/``）不能作文件名，落盘到 ``per_user_copy_name`` 的确定性别名
     * （右栏把路径项加成多项目配置组后需要载体）。不触碰 BetterGI 全局
     * ``User/ScriptGroup/{name}.json`` 同名实配。
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
     * 获取 zzz-od 实例（账号）列表
     * 返回 zzz-od 实例列表（供「快速导入」选择来源实例）。
     * @param scriptId
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static getZzzodInstancesApiApiScriptsZzzodInstancesGet(
        scriptId: string,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/instances',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 新建一条龙实例（直控实例管理）
     * 创建实例（最小空闲槽，避开原生与跨脚本 MAS 绑定槽），返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static addZzzodInstanceApiApiScriptsZzzodInstancesAddPost(
        requestBody: ZzzOdInstanceAddIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 重命名一条龙实例（直控实例管理）
     * 只改注册表 name（实例目录不变），返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static renameZzzodInstanceApiApiScriptsZzzodInstancesRenamePost(
        requestBody: ZzzOdInstanceRenameIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/rename',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 切换实例是否参与「全部实例」运行（直控实例管理）
     * 切换 active_in_od 标志位，返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static setZzzodInstanceActiveInOdApiApiScriptsZzzodInstancesActiveInOdPost(
        requestBody: ZzzOdInstanceFlagIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/active-in-od',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 把所选实例设为当前活跃（直控「选择即运行」）
     * 把目标实例设为注册表 active（其余清 False），返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static setZzzodActiveInstanceApiApiScriptsZzzodInstancesSetActivePost(
        requestBody: ZzzOdInstanceActiveIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/set-active',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 切换实例「运行前切换账号」（直控实例管理；一条龙原生能力）
     * 切换实例条目的 force_login_before_run（一条龙自己消费），返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static setZzzodInstanceForceLoginApiApiScriptsZzzodInstancesForceLoginPost(
        requestBody: ZzzOdInstanceForceLoginIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/force-login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 设置运行实例（直控；one_dragon.yml 全局 instance_run）
     * 白名单校验后写回全局 instance_run（与直控页当前编辑哪个实例无关）。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static setZzzodInstanceRunModeApiApiScriptsZzzodInstancesRunModePost(
        requestBody: ZzzOdInstanceRunModeIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/run-mode',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除一条龙实例（直控实例管理；受 MAS 绑定槽保护）
     * 删除注册表条目与实例目录，返回更新后的实例列表。
     * @param requestBody
     * @returns ZzzOdInstancesOut Successful Response
     * @throws ApiError
     */
    public static deleteZzzodInstanceApiApiScriptsZzzodInstancesDeletePost(
        requestBody: ZzzOdInstanceDeleteIn,
    ): CancelablePromise<ZzzOdInstancesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/instances/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取实例槽总览（原生实例 / MAS 绑定槽 / 无主残留）
     * 槽目录是 MAS 分配在一条龙安装目录里的，注册表与 GUI 都看不到。
     *
     * 这份对照表用于诊断「槽目录数与用户数对不上」（绑定但没跑过的槽没有目录）
     * 与定位无主残留。
     * @param scriptId
     * @returns ZzzOdSlotsOut Successful Response
     * @throws ApiError
     */
    public static getZzzodSlotsApiApiScriptsZzzodSlotsGet(
        scriptId: string,
    ): CancelablePromise<ZzzOdSlotsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/slots',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 清理无主实例槽（先归档进回收池再删目录）
     * 原生实例与被任一 ZzzOd 用户绑定的槽一律不动，返回实际回收的槽号。
     * @param requestBody
     * @returns ZzzOdSlotCleanOut Successful Response
     * @throws ApiError
     */
    public static cleanZzzodSlotsApiApiScriptsZzzodSlotsCleanPost(
        requestBody: ZzzOdSlotCleanIn,
    ): CancelablePromise<ZzzOdSlotCleanOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/slots/clean',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取实例槽回收池（被删用户/脚本留下的槽内容与备份池快照）
     * 槽目录按安装根指纹归池，跨脚本共享；只有 ``kind=slot`` 的条目可恢复。
     * @param scriptId
     * @returns ZzzOdRecycleOut Successful Response
     * @throws ApiError
     */
    public static getZzzodRecycleApiApiScriptsZzzodRecycleGet(
        scriptId: string,
    ): CancelablePromise<ZzzOdRecycleOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/recycle',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 清空实例槽回收池（删除后不可找回，不碰配置恢复池）
     * 只删 recycle 池；onedragon 原生池与 mas 配置恢复池不受影响。
     * @param requestBody
     * @returns ZzzOdRecycleClearOut Successful Response
     * @throws ApiError
     */
    public static clearZzzodRecycleApiApiScriptsZzzodRecycleClearPost(
        requestBody: ZzzOdRecycleClearIn,
    ): CancelablePromise<ZzzOdRecycleClearOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/recycle/clear',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 把回收池里的槽快照恢复给某个 MAS 用户（现有用户或新建用户，先存底）
     * 恢复的落点是**用户的绑定槽**（``targetUser`` 指定现有用户，或
     * ``newUserName`` 新建一个用户）——只物化内容而不建立绑定的恢复没有出口，
     * MAS 下次运行不会认领它。目标用户已有绑定槽时覆盖其内容，恢复前先存底。
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static restoreZzzodRecycleApiApiScriptsZzzodRecycleRestorePost(
        requestBody: ZzzOdRecycleRestoreIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/recycle/restore',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取预备编队列表（名称 + 绑定配队方案）
     * 读绑定槽（直控传 instanceIdx 读原生实例）的 team.yml（固定 20 个编队）。
     * @param scriptId
     * @param userId
     * @param instanceIdx
     * @returns ZzzOdTeamsOut Successful Response
     * @throws ApiError
     */
    public static getZzzodTeamsApiApiScriptsZzzodTeamsGet(
        scriptId: string,
        userId: string,
        instanceIdx?: (number | null),
    ): CancelablePromise<ZzzOdTeamsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/teams',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'instanceIdx': instanceIdx,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 整表保存预备编队（名称 + 绑定配队方案；成员按行保留）
     * 直控传 instanceIdx 直接写原生实例，缺省写用户绑定槽。
     * @param requestBody
     * @returns ZzzOdTeamsSaveOut Successful Response
     * @throws ApiError
     */
    public static saveZzzodTeamsApiApiScriptsZzzodTeamsSavePost(
        requestBody: ZzzOdTeamsSaveIn,
    ): CancelablePromise<ZzzOdTeamsSaveOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/teams/save',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取一条龙任务目录
     * 静态解析安装目录下的应用注册信息，供用户配置渲染任务卡片中文名。
     * @param scriptId
     * @returns ZzzOdCatalogOut Successful Response
     * @throws ApiError
     */
    public static getZzzodCatalogApiApiScriptsZzzodCatalogGet(
        scriptId: string,
    ): CancelablePromise<ZzzOdCatalogOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/catalog',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取任务级配置（字段元数据 + 当前值）
     * 返回任务可配置字段、选项与当前值（直控传 instanceIdx 读原生实例，否则读绑定槽）。
     * @param scriptId
     * @param userId
     * @param appId
     * @param instanceIdx
     * @returns ZzzOdAppConfigOut Successful Response
     * @throws ApiError
     */
    public static getZzzodAppConfigApiApiScriptsZzzodAppConfigGet(
        scriptId: string,
        userId: string,
        appId: string,
        instanceIdx?: (number | null),
    ): CancelablePromise<ZzzOdAppConfigOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/app-config',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'appId': appId,
                'instanceIdx': instanceIdx,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取任务计划的动态选项（副本级联树/配队方案/挑战配置）
     * 静态读取安装目录（compendium 数据 + 配置目录扫描），与一条龙原生 GUI 选项同源。
     * @param scriptId
     * @param appId
     * @returns ZzzOdTaskOptionsOut Successful Response
     * @throws ApiError
     */
    public static getZzzodTaskOptionsApiApiScriptsZzzodOptionsGet(
        scriptId: string,
        appId: string,
    ): CancelablePromise<ZzzOdTaskOptionsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/options',
            query: {
                'scriptId': scriptId,
                'appId': appId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存任务级配置（绑定槽；直控传 instanceIdx 直接写原生实例）
     * 字段白名单校验后写入 per-app YAML（缺省写用户绑定槽，直控写指定原生实例）。
     * @param requestBody
     * @returns ZzzOdAppConfigOut Successful Response
     * @throws ApiError
     */
    public static saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost(
        requestBody: ZzzOdAppConfigSaveIn,
    ): CancelablePromise<ZzzOdAppConfigOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/app-config/save',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取实例原生配置（直控页面表单数据）
     * 读取所选实例 game_account.yml 与 _group.yml（含默认值合并与任务目录并入）。
     * @param scriptId
     * @param instanceIdx
     * @returns ZzzOdNativeConfigOut Successful Response
     * @throws ApiError
     */
    public static getZzzodNativeConfigApiApiScriptsZzzodNativeConfigGet(
        scriptId: string,
        instanceIdx: number,
    ): CancelablePromise<ZzzOdNativeConfigOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/native-config',
            query: {
                'scriptId': scriptId,
                'instanceIdx': instanceIdx,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存实例原生配置（直控模式直接写回一条龙原始 YAML）
     * 白名单过滤后写回所选实例 game_account.yml、_group.yml、instance_run 与 after_done，随后回读最新数据。
     * @param requestBody
     * @returns ZzzOdNativeConfigOut Successful Response
     * @throws ApiError
     */
    public static saveZzzodNativeConfigApiApiScriptsZzzodNativeConfigSavePost(
        requestBody: ZzzOdNativeConfigIn,
    ): CancelablePromise<ZzzOdNativeConfigOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/native-config/save',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取一条龙两种启动器的安装情况与默认项
     * 渲染「启动器」下拉用（直控/用户两态通用）：未安装的启动器选项禁用变灰。
     * @param scriptId
     * @returns ZzzOdLauncherOut Successful Response
     * @throws ApiError
     */
    public static getZzzodLaunchersApiApiScriptsZzzodLaunchersGet(
        scriptId: string,
    ): CancelablePromise<ZzzOdLauncherOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/zzzod/launchers',
            query: {
                'scriptId': scriptId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 基于一条龙已有实例快速生成当前用户配置（覆盖前自动归档当前配置）
     * 把来源实例的账号信息与已启用任务编排写入本用户；覆盖前强制归档当前 MAS 槽配置，
     * 导入前状态可在「配置恢复」中找回。
     * @param requestBody
     * @returns ZzzOdImportOut Successful Response
     * @throws ApiError
     */
    public static importZzzodConfigApiApiScriptsZzzodImportPost(
        requestBody: ZzzOdImportIn,
    ): CancelablePromise<ZzzOdImportOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/zzzod/import',
            body: requestBody,
            mediaType: 'application/json',
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
     * 检查或执行 HSR 外部脚本更新
     * 手动检查或安装 M7A / SRA 的更新。
     *
     * 自动更新只在任务正常跑完后触发（``Update.AutoUpdateMode = AfterRun``），
     * 这个接口是唯一不必等一轮任务就能更新的入口。
     * @param requestBody
     * @returns HSRUpdateOut Successful Response
     * @throws ApiError
     */
    public static postHsrUpdateApiApiScriptsHsrUpdatePost(
        requestBody: HSRUpdateIn,
    ): CancelablePromise<HSRUpdateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/hsr/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 为 HSR 用户登录云·星穹铁道
     * 起该用户的云浏览器并用三月七的 ``game`` 任务等用户在窗口里登录。
     *
     * 阻塞到三月七退出为止（最长为登录等待 + 最长排队 + 余量），与正在运行的
     * 任务互斥：脚本运行中或三月七目录被占用时返回 409。成功后写
     * ``Cloud.LastLogin``。
     * @param requestBody
     * @returns HSRCloudLoginOut Successful Response
     * @throws ApiError
     */
    public static postHsrCloudLoginApiApiScriptsHsrCloudLoginPost(
        requestBody: HSRCloudLoginIn,
    ): CancelablePromise<HSRCloudLoginOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/hsr/cloud-login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取 HSR 托管配置字段
     * 返回原生动态托管字段。
     *
     * 传了用户 ID 时先做归属校验，再按该用户的配置来源决定表单读哪份计划：
     * 「脚本」读脚本共享计划，「用户」读该用户自己的计划；不传用户 ID 时读
     * 脚本共享计划。响应的 ``plan_owner`` 指明保存目标。
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
     * 获取 OK-NTE 配置文件列表及 schema
     * 获取 OK-NTE 配置文件列表及 schema 定义。
     * 读写用户快速配置目录，首次从已有来源初始化，不修改来源文件。
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
     * 列出配置备份（时间倒序；target 取值由专项定义，非法值返回 400）
     * 返回 ``items``（``time`` + 备份时点来源标注 ``mode``，倒序）与当前
     * 来源 ``mode``（仅三态池，供前端跨来源提示）；非法 target 返回 400。
     * @param scriptId
     * @param userId
     * @param target
     * @returns ConfigBackupListOut Successful Response
     * @throws ApiError
     */
    public static listConfigBackupsApiApiScriptsBackupListGet(
        scriptId: string,
        userId: string,
        target: string,
    ): CancelablePromise<ConfigBackupListOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/backup/list',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'target': target,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 按需归档目标池当前配置（指纹去重，无变化跳过；编辑界面进入/退出时机调用）
     * target 取值由专项池定义（如 zzz-od 的 mas/onedragon、ok-nte 的 mas/native）。
     * @param requestBody
     * @returns ConfigBackupEnsureOut Successful Response
     * @throws ApiError
     */
    public static ensureConfigBackupApiApiScriptsBackupEnsurePost(
        requestBody: ConfigBackupEnsureIn,
    ): CancelablePromise<ConfigBackupEnsureOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/backup/ensure',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 把指定备份恢复到目标位置（恢复前自动存底当前配置，误恢复可找回）
     * 恢复语义由专项池定义：脚本原生池恢复到脚本本体，MAS 用户池恢复到
     * 用户配置并按需回填前端表单。备份来自其他配置来源（脚本级/用户级）时
     * 由服务层把配置来源切回备份时点再恢复；提示由前端据备份列表与当前
     * 来源比对给出。
     * @param requestBody
     * @returns ConfigBackupRestoreOut Successful Response
     * @throws ApiError
     */
    public static restoreConfigBackupApiApiScriptsBackupRestorePost(
        requestBody: ConfigBackupRestoreIn,
    ): CancelablePromise<ConfigBackupRestoreOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/backup/restore',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 读取指定备份的配置摘要（纯读不恢复，供「预览配置」快速展示）
     * data 载荷结构由专项定义（前端按 target 消费）；非法 target 返回 400。
     * @param scriptId
     * @param userId
     * @param time
     * @param target
     * @returns ConfigBackupPreviewOut Successful Response
     * @throws ApiError
     */
    public static getConfigBackupPreviewApiApiScriptsBackupPreviewGet(
        scriptId: string,
        userId: string,
        time: string,
        target: string,
    ): CancelablePromise<ConfigBackupPreviewOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/backup/preview',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'time': time,
                'target': target,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 只读读取指定备份内一个文本文件（预览「查看原始文件」用，路径限归档内）
     * 路径越界/文件超限/池未实现查看能力均返回 400，message 说明原因。
     * @param scriptId
     * @param userId
     * @param time
     * @param target
     * @param path
     * @returns ConfigBackupFileOut Successful Response
     * @throws ApiError
     */
    public static getConfigBackupFileApiApiScriptsBackupFileGet(
        scriptId: string,
        userId: string,
        time: string,
        target: string,
        path: string,
    ): CancelablePromise<ConfigBackupFileOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/scripts/backup/file',
            query: {
                'scriptId': scriptId,
                'userId': userId,
                'time': time,
                'target': target,
                'path': path,
            },
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
     * 查询游戏社区日常活跃度
     * 查询游戏社区日常活动，不占用签到流程锁。
     * @param requestBody
     * @returns CommunityActivityOut Successful Response
     * @throws ApiError
     */
    public static queryCommunityActivityApiToolsCommunityActivityQueryPost(
        requestBody: CommunityActivityQueryIn,
    ): CancelablePromise<CommunityActivityOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/community/activity/query',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
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
     * 查询通知渠道描述
     * 返回通知渠道描述表，仅展示元数据，不含任何配置值。
     * @returns NotifyChannelsOut Successful Response
     * @throws ApiError
     */
    public static getNotifyChannelsApiSettingNotifyChannelsGet(): CancelablePromise<NotifyChannelsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/setting/notify/channels',
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
     * 检测虚拟显示驱动
     * 三段式检测虚拟显示驱动。
     *
     * 前两段验「能不能调用」，第三段真插一块屏再拆掉，验「有没有效果」——只做前两段
     * 会出现「设置页显示检测通过、无人值守时照样失败」的假信号。第三段会真的改变桌面
     * 拓扑，所以只挂在用户手动触发的按钮上，不在任务流程里自动跑。
     * @returns VirtualDisplayCheckOut Successful Response
     * @throws ApiError
     */
    public static checkVirtualDisplayApiSettingVirtualDisplayCheckPost(): CancelablePromise<VirtualDisplayCheckOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/virtual-display/check',
        });
    }
    /**
     * 立即拆除虚拟显示器
     * 用户明示要拆：真实显示器回来时的询问弹窗和设置页的「立即拆除」都走这里。
     *
     * 任务在不在跑都照办。拆完守卫的巡检照常：桌面上还有真实输出就什么都不做，一块都没有
     * 的话下一轮会重新挂上——要彻底停用得关开关。
     * @returns VirtualDisplayDetachOut Successful Response
     * @throws ApiError
     */
    public static detachVirtualDisplayApiSettingVirtualDisplayDetachPost(): CancelablePromise<VirtualDisplayDetachOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/virtual-display/detach',
        });
    }
    /**
     * 查询虚拟显示驱动状态
     * 只查驱动装没装、能不能调，不改变桌面拓扑。
     *
     * 设置页打开时自动调用，用来决定开关能不能打开。不做缓存也不持久化：一次 0.2ms，
     * 而存下来的状态只会变陈旧。
     * @returns VirtualDisplayCheckOut Successful Response
     * @throws ApiError
     */
    public static virtualDisplayStatusApiSettingVirtualDisplayStatusPost(): CancelablePromise<VirtualDisplayCheckOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/virtual-display/status',
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
     * 轮询状态，确认后返回 Passport App 或 Web 链路的完整 cookies。
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
    /**
     * 创建二维码
     * @returns SklandQrCreateOut Successful Response
     * @throws ApiError
     */
    public static qrCreateApiToolsSignSklandQrCreatePost(): CancelablePromise<SklandQrCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/skland/qr/create',
        });
    }
    /**
     * 轮询扫码状态
     * 确认后返回短时 scanCode，由前端随后提交保存。
     * @param requestBody
     * @returns SklandQrCheckOut Successful Response
     * @throws ApiError
     */
    public static qrCheckApiToolsSignSklandQrCheckPost(
        requestBody: SklandQrCheckIn,
    ): CancelablePromise<SklandQrCheckOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/skland/qr/check',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 保存森空岛 Token
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static qrSaveApiToolsSignSklandQrSavePost(
        requestBody: SklandQrSaveIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign/skland/qr/save',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
