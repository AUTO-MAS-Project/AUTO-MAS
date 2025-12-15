/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ADBScreenshotIn } from '../models/ADBScreenshotIn';
import type { ADBScreenshotOut } from '../models/ADBScreenshotOut';
import type { CheckImageAllIn } from '../models/CheckImageAllIn';
import type { CheckImageAnyIn } from '../models/CheckImageAnyIn';
import type { CheckImageIn } from '../models/CheckImageIn';
import type { CheckImageOut } from '../models/CheckImageOut';
import type { ComboBoxOut } from '../models/ComboBoxOut';
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
import type { NoticeOut } from '../models/NoticeOut';
import type { OCRScreenshotIn } from '../models/OCRScreenshotIn';
import type { OCRScreenshotOut } from '../models/OCRScreenshotOut';
import type { PlanGetIn } from '../models/PlanGetIn';
import type { PlanGetOut } from '../models/PlanGetOut';
import type { PowerOut } from '../models/PowerOut';
import type { QueueGetIn } from '../models/QueueGetIn';
import type { QueueGetOut } from '../models/QueueGetOut';
import type { QueueItemGetIn } from '../models/QueueItemGetIn';
import type { QueueItemGetOut } from '../models/QueueItemGetOut';
import type { ScriptGetIn } from '../models/ScriptGetIn';
import type { ScriptGetOut } from '../models/ScriptGetOut';
import type { SettingGetOut } from '../models/SettingGetOut';
import type { TimeSetGetIn } from '../models/TimeSetGetIn';
import type { TimeSetGetOut } from '../models/TimeSetGetOut';
import type { UpdateCheckIn } from '../models/UpdateCheckIn';
import type { UpdateCheckOut } from '../models/UpdateCheckOut';
import type { UserDeleteIn } from '../models/UserDeleteIn';
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
