/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { app__api__OutBase } from '../models/app__api__OutBase';
import type { app__models__schema__OutBase } from '../models/app__models__schema__OutBase';
import type { BackendHealthOut } from '../models/BackendHealthOut';
import type { BlueArchiveActivityIn } from '../models/BlueArchiveActivityIn';
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { CommunityActivityOut } from '../models/CommunityActivityOut';
import type { CommunityActivityQueryIn } from '../models/CommunityActivityQueryIn';
import type { DispatchIn } from '../models/DispatchIn';
import type { EmulatorDeleteIn } from '../models/EmulatorDeleteIn';
import type { GameCreateIn } from '../models/GameCreateIn';
import type { GameCreateOut } from '../models/GameCreateOut';
import type { GameDeleteIn } from '../models/GameDeleteIn';
import type { GameGetIn } from '../models/GameGetIn';
import type { GameGetOut } from '../models/GameGetOut';
import type { GameReorderIn } from '../models/GameReorderIn';
import type { GameSignAccountCreateOut } from '../models/GameSignAccountCreateOut';
import type { GameSignAccountDeleteIn } from '../models/GameSignAccountDeleteIn';
import type { GameSignAccountGetIn } from '../models/GameSignAccountGetIn';
import type { GameSignAccountReorderIn } from '../models/GameSignAccountReorderIn';
import type { GameSignAccountsListOut } from '../models/GameSignAccountsListOut';
import type { GameSignAccountUpdateIn } from '../models/GameSignAccountUpdateIn';
import type { GameTypesOut } from '../models/GameTypesOut';
import type { GameUpdateIn } from '../models/GameUpdateIn';
import type { GetStageIn } from '../models/GetStageIn';
import type { HistoryDataGetIn } from '../models/HistoryDataGetIn';
import type { HistoryDataGetOut } from '../models/HistoryDataGetOut';
import type { HistorySearchIn } from '../models/HistorySearchIn';
import type { HistorySearchOut } from '../models/HistorySearchOut';
import type { I18nLocaleIn } from '../models/I18nLocaleIn';
import type { I18nLocalesOut } from '../models/I18nLocalesOut';
import type { I18nMessagesOut } from '../models/I18nMessagesOut';
import type { InfoOut } from '../models/InfoOut';
import type { InstancesGetIn } from '../models/InstancesGetIn';
import type { InstancesGetOut } from '../models/InstancesGetOut';
import type { InstanceUpdateIn } from '../models/InstanceUpdateIn';
import type { NoticeOut } from '../models/NoticeOut';
import type { PlanCreateIn } from '../models/PlanCreateIn';
import type { PlanCreateOut } from '../models/PlanCreateOut';
import type { PlanDeleteIn } from '../models/PlanDeleteIn';
import type { PlanGetIn } from '../models/PlanGetIn';
import type { PlanGetOut } from '../models/PlanGetOut';
import type { PlanReorderIn } from '../models/PlanReorderIn';
import type { PlanUpdateIn } from '../models/PlanUpdateIn';
import type { PluginCatalogGetIn } from '../models/PluginCatalogGetIn';
import type { PluginCatalogGetOut } from '../models/PluginCatalogGetOut';
import type { PluginCatalogRefreshIn } from '../models/PluginCatalogRefreshIn';
import type { PluginCatalogUpdateIn } from '../models/PluginCatalogUpdateIn';
import type { PluginConfigGetIn } from '../models/PluginConfigGetIn';
import type { PluginConfigGetOut } from '../models/PluginConfigGetOut';
import type { PluginConfigUpdateIn } from '../models/PluginConfigUpdateIn';
import type { PluginRegistryGetIn } from '../models/PluginRegistryGetIn';
import type { PluginRegistryGetOut } from '../models/PluginRegistryGetOut';
import type { PluginRegistryUpdateIn } from '../models/PluginRegistryUpdateIn';
import type { PluginRuntimeListOut } from '../models/PluginRuntimeListOut';
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
import type { ScriptCreateIn } from '../models/ScriptCreateIn';
import type { ScriptCreateOut } from '../models/ScriptCreateOut';
import type { ScriptDeleteIn } from '../models/ScriptDeleteIn';
import type { ScriptGetIn } from '../models/ScriptGetIn';
import type { ScriptGetOut } from '../models/ScriptGetOut';
import type { ScriptReorderIn } from '../models/ScriptReorderIn';
import type { ScriptTypesOut } from '../models/ScriptTypesOut';
import type { ScriptUpdateIn } from '../models/ScriptUpdateIn';
import type { SearchAddIn } from '../models/SearchAddIn';
import type { SearchOut } from '../models/SearchOut';
import type { SettingGetOut } from '../models/SettingGetOut';
import type { SettingUpdateIn } from '../models/SettingUpdateIn';
import type { TaskCreateIn } from '../models/TaskCreateIn';
import type { TaskCreateOut } from '../models/TaskCreateOut';
import type { TaskGetIn } from '../models/TaskGetIn';
import type { TaskGetOut } from '../models/TaskGetOut';
import type { TaskRuntimeSnapshot } from '../models/TaskRuntimeSnapshot';
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
import type { UserReorderIn } from '../models/UserReorderIn';
import type { UserUpdateIn } from '../models/UserUpdateIn';
import type { VersionOut } from '../models/VersionOut';
import type { VirtualDisplayDetachOut } from '../models/VirtualDisplayDetachOut';
import type { WebhookCreateOut } from '../models/WebhookCreateOut';
import type { WebhookDeleteIn } from '../models/WebhookDeleteIn';
import type { WebhookGetIn } from '../models/WebhookGetIn';
import type { WebhookGetOut } from '../models/WebhookGetOut';
import type { WebhookInBase } from '../models/WebhookInBase';
import type { WebhookReorderIn } from '../models/WebhookReorderIn';
import type { WebhookTestIn } from '../models/WebhookTestIn';
import type { WebhookUpdateIn } from '../models/WebhookUpdateIn';
import type { WebSocketMetaOut } from '../models/WebSocketMetaOut';
import type { WSDialogRequestData } from '../models/WSDialogRequestData';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class Service {
    /**
     * 获取后端就绪状态
     * 返回后台初始化状态与受监督身份，commit 仅来自监督器注入。
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
     * 获取待处理弹窗初始快照
     * 返回当前未完成弹窗；WS 只承载后续请求与响应事件。
     * @returns WSDialogRequestData Successful Response
     * @throws ApiError
     */
    public static getPendingDialogsApiCoreDialogsPendingGet(): CancelablePromise<Array<WSDialogRequestData>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/core/dialogs/pending',
        });
    }
    /**
     * 关闭后端程序
     * 关闭后端程序：启动清理流程，完成后经主 WS 发送 backend.shutdown.ready
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static closeApiCoreClosePost(): CancelablePromise<app__models__schema__OutBase> {
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
        requestBody?: Record<string, any>,
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
     * 获取可选游戏/模拟器下拉框信息
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
     * 获取可选游戏多开实例下拉框信息
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static confirmNoticeApiInfoNoticeConfirmPost(): CancelablePromise<app__api__OutBase> {
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
     * 获取碧蓝档案活动数据（GameKee 中转）
     * 按服务器取回碧蓝档案的活动。
     *
     * 这里只做转发：把 GameKee 的响应原样交给前端，分类筛选与格式转换都由前端完成。
     * 之所以要绕一道后端，一是那个接口认自定义头、二是响应没给跨域头，浏览器直连取不到。
     *
     * GameKee 取不到时改用 SRA 托管的那份：那一份已经筛掉非活动条目，这里换成 GameKee
     * 的字段形状再交给前端，省得让前端认识第二套数据源。
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
     * 获取碧蓝档案活动图片（GameKee 中转）
     * 中转 GameKee 的图片。
     *
     * 那个 CDN 校验 Referer：带上它自己的站点才给图，页面直连（Referer 是本软件）会被拒。
     * 所以图片也由后端取回，前端只管引用这个地址。
     * @param url 图片地址
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getBluearchiveImageApiInfoBluearchiveImageGet(
        url: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/info/bluearchive/image',
            query: {
                'url': url,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取终末地版本图与版本名
     * 终末地的版本图地址与版本名（图是固定地址，前端再走图片中转取回）。
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static getEndfieldVersionArtApiInfoEndfieldVersionArtGet(): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/info/endfield/version-art',
        });
    }
    /**
     * 获取终末地活动图片（缩放后转发）
     * 把终末地的活动大图缩到横幅宽度再交给前端。
     * @param url 图片地址
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getEndfieldImageApiInfoEndfieldImageGet(
        url: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/info/endfield/image',
            query: {
                'url': url,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取明日方舟活动数据（PRTS 中转）
     * 取回明日方舟的活动一览。
     *
     * PRTS 的页面里已经带了活动名、分类、起止时间与配图，这里解析成前端好用的形状。
     * 最近两周一场活动都没有是正常情况（长草期），按空列表返回并照常缓存，
     * 不然前端会把「没有活动」当成接口出错反复重试。
     *
     * PRTS 在部分网络下会连不上、也挡浏览器直连，真取不到时改用 SRA 托管的那份活动列表
     * 顶上：数据没有活动分类，卡片上会少一列标签，但至少不是空的。
     * @returns InfoOut Successful Response
     * @throws ApiError
     */
    public static getArknightsActivityApiInfoArknightsActivityGet(): CancelablePromise<InfoOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/info/arknights/activity',
        });
    }
    /**
     * 获取星塔旅人活动数据（官网公告）
     * 取回星塔旅人的活动一览。
     *
     * 数据取自国服官网的活动公告：官网 CMS 不放开跨域、也认 Referer，所以由后端
     * 取回并按公告正文里的开放时间整理成与其它游戏一致的形状。
     *
     * 官网取不到、或者这一次一篇活动公告都没识别出来时，改用 SRA 托管的那份顶上：
     * 对方的抓取在它自己的服务器上完成，用户本机到不了官网也能看到活动。那份数据没有
     * 分类，按本模块给星塔旅人定的判据补一个，否则前端的横幅与常驻分组会全落空。
     *
     * Returns:
     * InfoOut: ``{"activities": [...]}``；两处都取不到时返回 ``code=500`` 的错误信封。
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
     * Get Task Runtime Snapshot
     * 读取统一派发器的运行快照，不启动任何任务。
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
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static stopTaskApiDispatchStopPost(
        requestBody: DispatchIn,
    ): CancelablePromise<app__models__schema__OutBase> {
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
     * 查询任务
     * @param requestBody
     * @returns TaskGetOut Successful Response
     * @throws ApiError
     */
    public static getTasksApiDispatchGetPost(
        requestBody: TaskGetIn,
    ): CancelablePromise<TaskGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/dispatch/get',
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
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static setPowerApiDispatchSetPowerPost(
        requestBody: PowerIn,
    ): CancelablePromise<app__models__schema__OutBase> {
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
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static cancelPowerTaskApiDispatchCancelPowerPost(): CancelablePromise<app__models__schema__OutBase> {
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
     * 获取工具设置。
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
     * 更新工具配置（仅 Group 字段；账号组走独立端点）。
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateToolsApiToolsUpdatePost(
        requestBody: ToolsUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 手动触发游戏社区签到。
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static manualGameSignApiToolsSignPost(): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/tools/sign',
        });
    }
    /**
     * 获取所有游戏签到账号组
     * 获取所有游戏签到账号组（PascalCase 形状）。
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
     * 添加游戏签到账号组（新账号无历史结果，无需清空）。
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
     * 获取游戏签到账号组详情（凭据明文，供编辑回显）。
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
     * 更新游戏签到账号组；空凭据占位不写入；凭据变更时重置签到日。
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateGameSignAccountApiToolsSignAccountUpdatePost(
        requestBody: GameSignAccountUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 删除游戏签到账号组（一并清除当天结果）。
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static deleteGameSignAccountApiToolsSignAccountDeletePost(
        requestBody: GameSignAccountDeleteIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 调整游戏签到账号组顺序。
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static reorderGameSignAccountsApiToolsSignAccountReorderPost(
        requestBody: GameSignAccountReorderIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 查询配置
     * 查询全局设置。
     * @returns SettingGetOut Successful Response
     * @throws ApiError
     */
    public static getSettingApiSettingGetPost(): CancelablePromise<SettingGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/get',
        });
    }
    /**
     * 更新配置
     * 更新全局设置（仅 Group 字段；``custom_webhooks`` 走独立端点）。
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateSettingApiSettingUpdatePost(
        requestBody: SettingUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 测试通知：置位 ``Setting.notify.test`` 触发器。
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static testNotifyApiSettingTestNotifyPost(): CancelablePromise<app__api__OutBase> {
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
     * @param requestBody
     * @returns WebhookCreateOut Successful Response
     * @throws ApiError
     */
    public static addWebhookApiSettingWebhookAddPost(
        requestBody?: (WebhookInBase | null),
    ): CancelablePromise<WebhookCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/webhook/add',
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateWebhookApiSettingWebhookUpdatePost(
        requestBody: WebhookUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static deleteWebhookApiSettingWebhookDeletePost(
        requestBody: WebhookDeleteIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static reorderWebhookApiSettingWebhookOrderPost(
        requestBody: WebhookReorderIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 测试自定义 Webhook：激活 Body 冷态并置位 ``info.test`` 触发器。
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static testWebhookApiSettingWebhookTestPost(
        requestBody: WebhookTestIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static downloadUpdateApiUpdateDownloadPost(
        version?: (string | null),
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static cancelUpdateDownloadApiUpdateCancelDownloadPost(): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/update/cancel-download',
        });
    }
    /**
     * 切换下载源到 CNB
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static switchUpdateDownloadToCnbApiUpdateSwitchToCnbPost(): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/update/switch-to-cnb',
        });
    }
    /**
     * 安装更新
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static installUpdateApiUpdateInstallPost(): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/update/install',
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateQueueApiQueueUpdatePost(
        requestBody: QueueUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static deleteQueueApiQueueDeletePost(
        requestBody: QueueDeleteIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static reorderQueueApiQueueOrderPost(
        requestBody: QueueReorderIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateTimeSetApiQueueTimeUpdatePost(
        requestBody: TimeSetUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static deleteTimeSetApiQueueTimeDeletePost(
        requestBody: TimeSetDeleteIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static reorderTimeSetApiQueueTimeOrderPost(
        requestBody: TimeSetReorderIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateItemApiQueueItemUpdatePost(
        requestBody: QueueItemUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static deleteItemApiQueueItemDeletePost(
        requestBody: QueueItemDeleteIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static reorderItemApiQueueItemOrderPost(
        requestBody: QueueItemReorderIn,
    ): CancelablePromise<app__api__OutBase> {
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
    public static getPlansApiPlanGetPost(
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
     * 更新计划表
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updatePlanApiPlanUpdatePost(
        requestBody: PlanUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static deletePlanApiPlanDeletePost(
        requestBody: PlanDeleteIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 计划表排序
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static orderPlansApiPlanOrderPost(
        requestBody: PlanReorderIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 可选脚本类型
     * @returns ScriptTypesOut Successful Response
     * @throws ApiError
     */
    public static listScriptTypesApiScriptsTypesPost(): CancelablePromise<ScriptTypesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/types',
        });
    }
    /**
     * 添加脚本
     * @param requestBody
     * @returns ScriptCreateOut Successful Response
     * @throws ApiError
     */
    public static addScriptApiScriptsAddPost(
        requestBody?: ScriptCreateIn,
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
     * 查询脚本
     * @param requestBody
     * @returns ScriptGetOut Successful Response
     * @throws ApiError
     */
    public static getScriptsApiScriptsGetPost(
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
     * 更新脚本
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateScriptApiScriptsUpdatePost(
        requestBody: ScriptUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static deleteScriptApiScriptsDeletePost(
        requestBody: ScriptDeleteIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 脚本排序
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static orderScriptsApiScriptsOrderPost(
        requestBody: ScriptReorderIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 添加用户
     * @param requestBody
     * @returns UserCreateOut Successful Response
     * @throws ApiError
     */
    public static addUserApiScriptsUserAddPost(
        requestBody: UserGetIn,
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
     * 查询用户
     * @param requestBody
     * @returns UserGetOut Successful Response
     * @throws ApiError
     */
    public static getUsersApiScriptsUserGetPost(
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
     * 更新用户
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateUserApiScriptsUserUpdatePost(
        requestBody: UserUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static deleteUserApiScriptsUserDeletePost(
        requestBody: UserDeleteIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 用户排序
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static orderUsersApiScriptsUserOrderPost(
        requestBody: UserReorderIn,
    ): CancelablePromise<app__api__OutBase> {
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
     * 可选游戏类型
     * @returns GameTypesOut Successful Response
     * @throws ApiError
     */
    public static listGameTypesApiGamesTypesPost(): CancelablePromise<GameTypesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/types',
        });
    }
    /**
     * 添加游戏
     * @param requestBody
     * @returns GameCreateOut Successful Response
     * @throws ApiError
     */
    public static addGameApiGamesAddPost(
        requestBody?: GameCreateIn,
    ): CancelablePromise<GameCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询游戏
     * @param requestBody
     * @returns GameGetOut Successful Response
     * @throws ApiError
     */
    public static getGamesApiGamesGetPost(
        requestBody: GameGetIn,
    ): CancelablePromise<GameGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新游戏
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateGameApiGamesUpdatePost(
        requestBody: GameUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除游戏
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static deleteGameApiGamesDeletePost(
        requestBody: GameDeleteIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/delete',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 游戏排序
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static orderGamesApiGamesOrderPost(
        requestBody: GameReorderIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/order',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询游戏设备
     * @param requestBody
     * @returns InstancesGetOut Successful Response
     * @throws ApiError
     */
    public static getInstancesApiGamesInstancesGetPost(
        requestBody: InstancesGetIn,
    ): CancelablePromise<InstancesGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/instances/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 更新游戏设备
     * @param requestBody
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static updateInstanceApiGamesInstancesUpdatePost(
        requestBody: InstanceUpdateIn,
    ): CancelablePromise<app__api__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/instances/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 搜索可加载游戏
     * @returns SearchOut Successful Response
     * @throws ApiError
     */
    public static searchGamesApiGamesSearchPost(): CancelablePromise<SearchOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/search',
        });
    }
    /**
     * 将搜索结果写入游戏配置
     * @param requestBody
     * @returns GameCreateOut Successful Response
     * @throws ApiError
     */
    public static addSearchedGameApiGamesSearchAddPost(
        requestBody: SearchAddIn,
    ): CancelablePromise<GameCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/search/add',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询插件注册表配置
     * @param requestBody
     * @returns PluginRegistryGetOut Successful Response
     * @throws ApiError
     */
    public static getPluginRegistryApiPluginRegistryGetPost(
        requestBody: PluginRegistryGetIn,
    ): CancelablePromise<PluginRegistryGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_registry/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改插件注册表项（仅 enable/disable/reload/uninstall Trigger）
     * @param requestBody
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static updatePluginRegistryApiPluginRegistryUpdatePost(
        requestBody: PluginRegistryUpdateIn,
    ): CancelablePromise<app__models__schema__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_registry/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询插件目录配置
     * @param requestBody
     * @returns PluginCatalogGetOut Successful Response
     * @throws ApiError
     */
    public static getPluginCatalogApiPluginCatalogGetPost(
        requestBody: PluginCatalogGetIn,
    ): CancelablePromise<PluginCatalogGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_catalog/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改目录项（透传全部字段）
     * @param requestBody
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static updatePluginCatalogApiPluginCatalogUpdatePost(
        requestBody: PluginCatalogUpdateIn,
    ): CancelablePromise<app__models__schema__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_catalog/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 从索引全量刷新目录并写入配置（读列表请再调 get）
     * @param requestBody
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static refreshPluginCatalogApiPluginCatalogRefreshPost(
        requestBody?: PluginCatalogRefreshIn,
    ): CancelablePromise<app__models__schema__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_catalog/refresh',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询插件自有配置（与注册表同一 uid）
     * @param requestBody
     * @returns PluginConfigGetOut Successful Response
     * @throws ApiError
     */
    public static getPluginConfigApiPluginConfigGetPost(
        requestBody: PluginConfigGetIn,
    ): CancelablePromise<PluginConfigGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_config/get',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改插件自有配置（与注册表同一 uid）
     * @param requestBody
     * @returns app__models__schema__OutBase Successful Response
     * @throws ApiError
     */
    public static updatePluginConfigApiPluginConfigUpdatePost(
        requestBody: PluginConfigUpdateIn,
    ): CancelablePromise<app__models__schema__OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_config/update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 列出已加载插件（运行时）
     * @returns PluginRuntimeListOut Successful Response
     * @throws ApiError
     */
    public static listPluginsApiPluginListPost(): CancelablePromise<PluginRuntimeListOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin/list',
        });
    }
    /**
     * Get Messages
     * 返回可直接交给 Vue I18n 的 messages。
     * @param locale
     * @returns I18nMessagesOut Successful Response
     * @throws ApiError
     */
    public static getMessagesApiI18NMessagesGet(
        locale?: (string | null),
    ): CancelablePromise<I18nMessagesOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/i18n/messages',
            query: {
                'locale': locale,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Locales
     * 返回当前语言、回退语言和可用语言。
     * @returns I18nLocalesOut Successful Response
     * @throws ApiError
     */
    public static getLocalesApiI18NLocalesGet(): CancelablePromise<I18nLocalesOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/i18n/locales',
        });
    }
    /**
     * Set Locale
     * 设置后端当前 locale 并广播资源变更。
     * @param requestBody
     * @returns I18nLocalesOut Successful Response
     * @throws ApiError
     */
    public static setLocaleApiI18NLocalePut(
        requestBody: I18nLocaleIn,
    ): CancelablePromise<I18nLocalesOut> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/i18n/locale',
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
     * @returns app__api__OutBase Successful Response
     * @throws ApiError
     */
    public static qrSaveApiToolsSignMiyousheQrSavePost(
        requestBody: QrSaveIn,
    ): CancelablePromise<app__api__OutBase> {
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
