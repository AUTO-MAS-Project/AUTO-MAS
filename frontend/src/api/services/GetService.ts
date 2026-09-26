/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ADBScreenshotIn } from '../models/ADBScreenshotIn';
import type { ADBScreenshotOut } from '../models/ADBScreenshotOut';
import type { BlueArchiveActivityIn } from '../models/BlueArchiveActivityIn';
import type { Body_get_maa_cultivate_operators_api_scripts_maa_cultivate_operators_post } from '../models/Body_get_maa_cultivate_operators_api_scripts_maa_cultivate_operators_post';
import type { Body_get_maa_depot_inventory_api_scripts_maa_depot_inventory_post } from '../models/Body_get_maa_depot_inventory_api_scripts_maa_depot_inventory_post';
import type { Body_get_maa_depot_stage_candidates_api_scripts_maa_depot_stage_candidates_post } from '../models/Body_get_maa_depot_stage_candidates_api_scripts_maa_depot_stage_candidates_post';
import type { CheckImageAllIn } from '../models/CheckImageAllIn';
import type { CheckImageAnyIn } from '../models/CheckImageAnyIn';
import type { CheckImageIn } from '../models/CheckImageIn';
import type { CheckImageOut } from '../models/CheckImageOut';
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { CultivatePreviewIn } from '../models/CultivatePreviewIn';
import type { CultivatePreviewOut } from '../models/CultivatePreviewOut';
import type { Emulator2DevicesIn } from '../models/Emulator2DevicesIn';
import type { Emulator2DevicesOut } from '../models/Emulator2DevicesOut';
import type { Emulator2InstanceDeleteIn } from '../models/Emulator2InstanceDeleteIn';
import type { Emulator2InstanceDeletePreviewOut } from '../models/Emulator2InstanceDeletePreviewOut';
import type { Emulator2PathRemoveIn } from '../models/Emulator2PathRemoveIn';
import type { Emulator2PathRemovePreviewOut } from '../models/Emulator2PathRemovePreviewOut';
import type { Emulator2SearchIn } from '../models/Emulator2SearchIn';
import type { Emulator2SearchOut } from '../models/Emulator2SearchOut';
import type { EmulatorDeleteIn } from '../models/EmulatorDeleteIn';
import type { EmulatorGetIn } from '../models/EmulatorGetIn';
import type { EmulatorGetOut } from '../models/EmulatorGetOut';
import type { EmulatorSearchOut } from '../models/EmulatorSearchOut';
import type { EmulatorStatusOut } from '../models/EmulatorStatusOut';
import type { GetStageIn } from '../models/GetStageIn';
import type { HistoryDataGetIn } from '../models/HistoryDataGetIn';
import type { HistoryDataGetOut } from '../models/HistoryDataGetOut';
import type { HistorySearchIn } from '../models/HistorySearchIn';
import type { HistorySearchOut } from '../models/HistorySearchOut';
import type { InfoOut } from '../models/InfoOut';
import type { MaaCultivateOperatorsOut } from '../models/MaaCultivateOperatorsOut';
import type { MaaDepotInventoryOut } from '../models/MaaDepotInventoryOut';
import type { MaaEndOptionsOut } from '../models/MaaEndOptionsOut';
import type { NoticeOut } from '../models/NoticeOut';
import type { NotifyChannelsOut } from '../models/NotifyChannelsOut';
import type { OCRScreenshotIn } from '../models/OCRScreenshotIn';
import type { OCRScreenshotOut } from '../models/OCRScreenshotOut';
import type { PlanComboxIn } from '../models/PlanComboxIn';
import type { PlanGetIn } from '../models/PlanGetIn';
import type { PlanGetOut } from '../models/PlanGetOut';
import type { PowerCountdownSnapshot } from '../models/PowerCountdownSnapshot';
import type { PowerOut } from '../models/PowerOut';
import type { QueueGetIn } from '../models/QueueGetIn';
import type { QueueGetOut } from '../models/QueueGetOut';
import type { QueueItemGetIn } from '../models/QueueItemGetIn';
import type { QueueItemGetOut } from '../models/QueueItemGetOut';
import type { ScriptDeleteIn } from '../models/ScriptDeleteIn';
import type { ScriptGetIn } from '../models/ScriptGetIn';
import type { ScriptGetOut } from '../models/ScriptGetOut';
import type { SettingGetOut } from '../models/SettingGetOut';
import type { TaskRuntimeSnapshot } from '../models/TaskRuntimeSnapshot';
import type { TimeSetGetIn } from '../models/TimeSetGetIn';
import type { TimeSetGetOut } from '../models/TimeSetGetOut';
import type { ToolsGetOut } from '../models/ToolsGetOut';
import type { UpdateCheckIn } from '../models/UpdateCheckIn';
import type { UpdateCheckOut } from '../models/UpdateCheckOut';
import type { UpdateDownloadSnapshot } from '../models/UpdateDownloadSnapshot';
import type { UserConfigDirIn } from '../models/UserConfigDirIn';
import type { UserConfigDirOut } from '../models/UserConfigDirOut';
import type { UserDeleteIn } from '../models/UserDeleteIn';
import type { UserGetIn } from '../models/UserGetIn';
import type { UserGetOut } from '../models/UserGetOut';
import type { UserInfrastPlanComboxOut } from '../models/UserInfrastPlanComboxOut';
import type { UserInfrastPlanSelectOut } from '../models/UserInfrastPlanSelectOut';
import type { VersionOut } from '../models/VersionOut';
import type { VirtualDisplayCheckOut } from '../models/VirtualDisplayCheckOut';
import type { WebhookGetIn } from '../models/WebhookGetIn';
import type { WebhookGetOut } from '../models/WebhookGetOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class GetService {
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
     * 搜索可加入 Emulator 2.0 的模拟器
     * 列出本机模拟器并逐条判定。不可添加的**也会列出**并给出原因枚举。
     * @param requestBody
     * @returns Emulator2SearchOut Successful Response
     * @throws ApiError
     */
    public static searchEmulatorsApiEmulator2SearchPost(
        requestBody?: Emulator2SearchIn,
    ): CancelablePromise<Emulator2SearchOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/search',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 预览移除模拟器路径的影响
     * 只读。列出会失效的设备号与受影响的脚本，供确认页使用。
     * @param requestBody
     * @returns Emulator2PathRemovePreviewOut Successful Response
     * @throws ApiError
     */
    public static previewRemovePathApiEmulator2PathsRemovePreviewPost(
        requestBody: Emulator2PathRemoveIn,
    ): CancelablePromise<Emulator2PathRemovePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/paths/remove/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 查询合并后的设备列表
     * 合并多条安装的实例。键是设备号，另附模拟器自己的实例索引。
     *
     * 枚举失败的安装标 ``unavailable``——一次枚举失败不等于实例被删除，
     * 既不写墓碑也不影响下次恢复。``withSettings=false`` 只取状态，给轮询用。
     * @param requestBody
     * @returns Emulator2DevicesOut Successful Response
     * @throws ApiError
     */
    public static listDevicesApiEmulator2DevicesPost(
        requestBody: Emulator2DevicesIn,
    ): CancelablePromise<Emulator2DevicesOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/devices',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 预览删除实例的影响
     * 只读。列出绑定了该设备号的脚本，供确认页使用。
     * @param requestBody
     * @returns Emulator2InstanceDeletePreviewOut Successful Response
     * @throws ApiError
     */
    public static previewDeleteInstanceApiEmulator2InstancesDeletePreviewPost(
        requestBody: Emulator2InstanceDeleteIn,
    ): CancelablePromise<Emulator2InstanceDeletePreviewOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/instances/delete/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
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
     * 获取窗口截图
     * 根据窗口标题获取截图，返回Base64编码的图像数据
     *
     * Args:
     * params: 截图参数
     * - window_title: 窗口标题关键字
     * - should_preprocess: 是否预处理图片区域（默认True）
     * - aspect_ratio_width: 宽高比宽度（默认16）
     * - aspect_ratio_height: 宽高比高度（默认9）
     * - region: 自定义截图区域，格式为 (left, top, width, height)
     *
     * Returns:
     * OCRScreenshotOut: 包含Base64编码的截图和区域信息
     * @param requestBody
     * @returns OCRScreenshotOut Successful Response
     * @throws ApiError
     */
    public static getScreenshotApiOcrScreenshotPost(
        requestBody: OCRScreenshotIn,
    ): CancelablePromise<OCRScreenshotOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/screenshot',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 通过ADB获取设备截图
     * 通过 ADB 端口获取 Android 设备/模拟器截图，返回Base64编码的图像数据
     *
     * 支持两种截图方法：
     * 1. screencap PNG 方法（推荐）：速度快，直接获取 PNG 图像
     * 2. screencap raw 方法：获取原始像素数据，适用于某些不支持 PNG 的设备
     *
     * Args:
     * params: ADB 截图参数
     * - adb_path: ADB 可执行文件的路径
     * - serial: 设备序列号，格式如 "127.0.0.1:5555" 或 "emulator-5554"
     * - use_screencap: 是否使用 screencap PNG 方法（默认True）
     *
     * Returns:
     * ADBScreenshotOut: 包含Base64编码的截图和设备信息
     * @param requestBody
     * @returns ADBScreenshotOut Successful Response
     * @throws ApiError
     */
    public static getScreenshotAdbApiOcrScreenshotAdbPost(
        requestBody: ADBScreenshotIn,
    ): CancelablePromise<ADBScreenshotOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/screenshot/adb',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 检查是否存在指定图像
     * 截图并查找是否存在图片内的内容
     *
     * Args:
     * params: 检查图像参数
     * - window_title: 窗口标题关键字
     * - image_path: 要查找的图片路径
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     * - threshold: 图像匹配阈值，范围 0-1，默认 0.8
     *
     * Returns:
     * CheckImageOut: 包含查找结果和尝试次数
     * @param requestBody
     * @returns CheckImageOut Successful Response
     * @throws ApiError
     */
    public static checkImageApiOcrCheckImagePost(
        requestBody: CheckImageIn,
    ): CancelablePromise<CheckImageOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/check/image',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 检查是否存在任意一个指定图像
     * 截图并查找是否存在列表中任意一张图片的内容
     *
     * Args:
     * params: 检查图像参数
     * - window_title: 窗口标题关键字
     * - image_paths: 要查找的图片路径列表
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     * - threshold: 图像匹配阈值，范围 0-1，默认 0.8
     *
     * Returns:
     * CheckImageOut: 包含查找结果和尝试次数
     * @param requestBody
     * @returns CheckImageOut Successful Response
     * @throws ApiError
     */
    public static checkImageAnyApiOcrCheckImageAnyPost(
        requestBody: CheckImageAnyIn,
    ): CancelablePromise<CheckImageOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/check/image/any',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 检查是否存在所有指定图像
     * 截图并查找是否存在列表中所有图片的内容
     *
     * Args:
     * params: 检查图像参数
     * - window_title: 窗口标题关键字
     * - image_paths: 要查找的图片路径列表
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     * - threshold: 图像匹配阈值，范围 0-1，默认 0.8
     *
     * Returns:
     * CheckImageOut: 包含查找结果和尝试次数
     * @param requestBody
     * @returns CheckImageOut Successful Response
     * @throws ApiError
     */
    public static checkImageAllApiOcrCheckImageAllPost(
        requestBody: CheckImageAllIn,
    ): CancelablePromise<CheckImageOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/check/image/all',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
