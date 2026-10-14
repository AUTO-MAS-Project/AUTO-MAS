/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ADBScreenshotIn } from '../models/ADBScreenshotIn';
import type { ADBScreenshotOut } from '../models/ADBScreenshotOut';
import type { BlueArchiveActivityIn } from '../models/BlueArchiveActivityIn';
import type { CheckImageAllIn } from '../models/CheckImageAllIn';
import type { CheckImageAnyIn } from '../models/CheckImageAnyIn';
import type { CheckImageIn } from '../models/CheckImageIn';
import type { CheckImageOut } from '../models/CheckImageOut';
import type { ComboBoxOut } from '../models/ComboBoxOut';
import type { EmulatorDeleteIn } from '../models/EmulatorDeleteIn';
import type { GameGetIn } from '../models/GameGetIn';
import type { GameGetOut } from '../models/GameGetOut';
import type { GameTypesOut } from '../models/GameTypesOut';
import type { GetStageIn } from '../models/GetStageIn';
import type { HistoryDataGetIn } from '../models/HistoryDataGetIn';
import type { HistoryDataGetOut } from '../models/HistoryDataGetOut';
import type { HistorySearchIn } from '../models/HistorySearchIn';
import type { HistorySearchOut } from '../models/HistorySearchOut';
import type { InfoOut } from '../models/InfoOut';
import type { InstancesGetIn } from '../models/InstancesGetIn';
import type { InstancesGetOut } from '../models/InstancesGetOut';
import type { NoticeOut } from '../models/NoticeOut';
import type { OCRScreenshotIn } from '../models/OCRScreenshotIn';
import type { OCRScreenshotOut } from '../models/OCRScreenshotOut';
import type { PlanGetIn } from '../models/PlanGetIn';
import type { PlanGetOut } from '../models/PlanGetOut';
import type { PluginCatalogGetIn } from '../models/PluginCatalogGetIn';
import type { PluginCatalogGetOut } from '../models/PluginCatalogGetOut';
import type { PluginConfigGetIn } from '../models/PluginConfigGetIn';
import type { PluginConfigGetOut } from '../models/PluginConfigGetOut';
import type { PluginRegistryGetIn } from '../models/PluginRegistryGetIn';
import type { PluginRegistryGetOut } from '../models/PluginRegistryGetOut';
import type { PluginRuntimeListOut } from '../models/PluginRuntimeListOut';
import type { PowerCountdownSnapshot } from '../models/PowerCountdownSnapshot';
import type { PowerOut } from '../models/PowerOut';
import type { QueueGetIn } from '../models/QueueGetIn';
import type { QueueGetOut } from '../models/QueueGetOut';
import type { QueueItemGetIn } from '../models/QueueItemGetIn';
import type { QueueItemGetOut } from '../models/QueueItemGetOut';
import type { ScriptGetIn } from '../models/ScriptGetIn';
import type { ScriptGetOut } from '../models/ScriptGetOut';
import type { ScriptTypesOut } from '../models/ScriptTypesOut';
import type { SearchOut } from '../models/SearchOut';
import type { SettingGetOut } from '../models/SettingGetOut';
import type { TaskGetIn } from '../models/TaskGetIn';
import type { TaskGetOut } from '../models/TaskGetOut';
import type { TaskRuntimeSnapshot } from '../models/TaskRuntimeSnapshot';
import type { TimeSetGetIn } from '../models/TimeSetGetIn';
import type { TimeSetGetOut } from '../models/TimeSetGetOut';
import type { ToolsGetOut } from '../models/ToolsGetOut';
import type { UpdateCheckIn } from '../models/UpdateCheckIn';
import type { UpdateCheckOut } from '../models/UpdateCheckOut';
import type { UpdateDownloadSnapshot } from '../models/UpdateDownloadSnapshot';
import type { UserGetIn } from '../models/UserGetIn';
import type { UserGetOut } from '../models/UserGetOut';
import type { VersionOut } from '../models/VersionOut';
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
}
