/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ClickImageIn } from '../models/ClickImageIn';
import type { ClickOut } from '../models/ClickOut';
import type { ClickTextIn } from '../models/ClickTextIn';
import type { DispatchIn } from '../models/DispatchIn';
import type { EmulatorOperateIn } from '../models/EmulatorOperateIn';
import type { OutBase } from '../models/OutBase';
import type { PowerIn } from '../models/PowerIn';
import type { ScriptFileIn } from '../models/ScriptFileIn';
import type { ScriptUploadIn } from '../models/ScriptUploadIn';
import type { TaskCreateIn } from '../models/TaskCreateIn';
import type { TaskCreateOut } from '../models/TaskCreateOut';
import type { WebhookTestIn } from '../models/WebhookTestIn';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ActionService {
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
     * 下载更新
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static downloadUpdateApiUpdateDownloadPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/update/download',
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
     * 点击指定图像位置
     * 截图、查找并点击与图像一致的位置
     *
     * Args:
     * params: 点击图像参数
     * - window_title: 窗口标题关键字
     * - image_path: 要查找并点击的图片路径
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     * - threshold: 图像匹配阈值，范围 0-1，默认 0.8
     *
     * Returns:
     * ClickOut: 包含点击结果和尝试次数
     * @param requestBody
     * @returns ClickOut Successful Response
     * @throws ApiError
     */
    public static clickImageApiOcrClickImagePost(
        requestBody: ClickImageIn,
    ): CancelablePromise<ClickOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/click/image',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 点击指定文字位置
     * 截图、OCR识别并点击与文字一致的位置
     *
     * Args:
     * params: 点击文字参数
     * - window_title: 窗口标题关键字
     * - text: 要查找并点击的文字内容
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     *
     * Returns:
     * ClickOut: 包含点击结果和尝试次数
     * @param requestBody
     * @returns ClickOut Successful Response
     * @throws ApiError
     */
    public static clickTextApiOcrClickTextPost(
        requestBody: ClickTextIn,
    ): CancelablePromise<ClickOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/click/text',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
