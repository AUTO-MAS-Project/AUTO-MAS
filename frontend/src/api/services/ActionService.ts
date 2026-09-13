/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ClickImageIn } from '../models/ClickImageIn';
import type { ClickOut } from '../models/ClickOut';
import type { ClickTextIn } from '../models/ClickTextIn';
import type { DispatchIn } from '../models/DispatchIn';
import type { Emulator2DevicesIn } from '../models/Emulator2DevicesIn';
import type { Emulator2GuardCaptureOut } from '../models/Emulator2GuardCaptureOut';
import type { Emulator2SettingsApplyAllIn } from '../models/Emulator2SettingsApplyAllIn';
import type { Emulator2SettingsApplyAllOut } from '../models/Emulator2SettingsApplyAllOut';
import type { Emulator2SettingsApplyIn } from '../models/Emulator2SettingsApplyIn';
import type { Emulator2SettingsApplyOut } from '../models/Emulator2SettingsApplyOut';
import type { Emulator2StableModeIn } from '../models/Emulator2StableModeIn';
import type { Emulator2StoreOpenIn } from '../models/Emulator2StoreOpenIn';
import type { Emulator2StoreOpenOut } from '../models/Emulator2StoreOpenOut';
import type { EmulatorOperateIn } from '../models/EmulatorOperateIn';
import type { OutBase } from '../models/OutBase';
import type { PatternDebugIn } from '../models/PatternDebugIn';
import type { PatternDebugOut } from '../models/PatternDebugOut';
import type { PowerIn } from '../models/PowerIn';
import type { ScriptConfigImportIn } from '../models/ScriptConfigImportIn';
import type { ScriptUploadIn } from '../models/ScriptUploadIn';
import type { ShareAuthStatusOut } from '../models/ShareAuthStatusOut';
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
     * 分享脚本配置到配置中心
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
     * 打开游戏中心
     * 在一台**已在线**的设备上打开模拟器自带的游戏中心。
     *
     * 雷电纯净模式会把游戏中心从桌面藏掉，这是它唯一的图形入口。
     * 拉不起来返回 ``ok=false`` 和一句说明，不算接口错误；只有设备号解析不出来才是 500。
     * @param requestBody
     * @returns Emulator2StoreOpenOut Successful Response
     * @throws ApiError
     */
    public static openStoreApiEmulator2InstancesStoreOpenPost(
        requestBody: Emulator2StoreOpenIn,
    ): CancelablePromise<Emulator2StoreOpenOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/instances/store/open',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改实例设置
     * 写一台设备的设置。
     *
     * 只提交用户改过的字段；``expected`` 与文件现状对不上就拒绝写入并交回冲突字段，
     * 绝不把表单打开时的旧值整片盖回去。
     * @param requestBody
     * @returns Emulator2SettingsApplyOut Successful Response
     * @throws ApiError
     */
    public static applySettingsApiEmulator2SettingsApplyPost(
        requestBody: Emulator2SettingsApplyIn,
    ): CancelablePromise<Emulator2SettingsApplyOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/settings/apply',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 批量修改全部实例设置
     * 把同一组设置写到全部实例上。
     *
     * 没有勾选也没有冲突比对——点它就是明确要求「所有实例都设成这组值」。
     * 一台失败不影响其余，逐台交回结果。
     * @param requestBody
     * @returns Emulator2SettingsApplyAllOut Successful Response
     * @throws ApiError
     */
    public static applySettingsToAllApiEmulator2SettingsApplyAllPost(
        requestBody: Emulator2SettingsApplyAllIn,
    ): CancelablePromise<Emulator2SettingsApplyAllOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/settings/apply-all',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 应用稳定模式
     * 把设备切进稳定模式：关掉会干扰截图识别的模拟器功能。
     *
     * ``slots`` 留空表示全部。每台交回实际改动了哪几项；已经安全的返回空改动列表。
     * **关掉稳定模式不由这个接口负责**——我们不知道用户原来想要什么值，不替他猜。
     * @param requestBody
     * @returns Emulator2SettingsApplyAllOut Successful Response
     * @throws ApiError
     */
    public static applyStableModeApiEmulator2StableModeApplyPost(
        requestBody: Emulator2StableModeIn,
    ): CancelablePromise<Emulator2SettingsApplyAllOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/stable-mode/apply',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 记录配置守卫的基准
     * 把当前所有设备的设置记成守卫基准。开启守卫时调一次。
     *
     * 只记用户显式设过的字段：模拟器默认值和从没设过的项没有「应该是什么」可言，
     * 写进基准等于替用户决定。
     * @param requestBody
     * @returns Emulator2GuardCaptureOut Successful Response
     * @throws ApiError
     */
    public static captureBaselinesApiEmulator2GuardCapturePost(
        requestBody: Emulator2DevicesIn,
    ): CancelablePromise<Emulator2GuardCaptureOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/emulator2/guard/capture',
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
     * 发起配置中心浏览器授权
     * @returns ShareAuthStatusOut Successful Response
     * @throws ApiError
     */
    public static startShareAuthApiShareAuthStartPost(): CancelablePromise<ShareAuthStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/share/auth/start',
        });
    }
    /**
     * 取消等待中的配置中心授权
     * @returns ShareAuthStatusOut Successful Response
     * @throws ApiError
     */
    public static cancelShareAuthApiShareAuthCancelPost(): CancelablePromise<ShareAuthStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/share/auth/cancel',
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
