/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ClickImageIn } from '../models/ClickImageIn';
import type { ClickOut } from '../models/ClickOut';
import type { ClickTextIn } from '../models/ClickTextIn';
import type { DispatchIn } from '../models/DispatchIn';
import type { GameBatchIn } from '../models/GameBatchIn';
import type { GameCreateIn } from '../models/GameCreateIn';
import type { GameGetOut } from '../models/GameGetOut';
import type { GameIdIn } from '../models/GameIdIn';
import type { GameSearchOut } from '../models/GameSearchOut';
import type { GameSettingsOut } from '../models/GameSettingsOut';
import type { MaaEndLogBundleIn } from '../models/MaaEndLogBundleIn';
import type { MaaEndLogBundleOut } from '../models/MaaEndLogBundleOut';
import type { ObsReplaySaveOut } from '../models/ObsReplaySaveOut';
import type { OutBase } from '../models/OutBase';
import type { PatternDebugIn } from '../models/PatternDebugIn';
import type { PatternDebugOut } from '../models/PatternDebugOut';
import type { PluginCatalogRefreshIn } from '../models/PluginCatalogRefreshIn';
import type { PluginInstallationOut } from '../models/PluginInstallationOut';
import type { PluginInstallationRestartIn } from '../models/PluginInstallationRestartIn';
import type { PowerIn } from '../models/PowerIn';
import type { ScriptConfigImportIn } from '../models/ScriptConfigImportIn';
import type { ScriptUploadIn } from '../models/ScriptUploadIn';
import type { ShareAppearanceDescriptionIn } from '../models/ShareAppearanceDescriptionIn';
import type { ShareAppearanceDescriptionOut } from '../models/ShareAppearanceDescriptionOut';
import type { ShareAppearanceUploadIn } from '../models/ShareAppearanceUploadIn';
import type { ShareAppearanceUploadOut } from '../models/ShareAppearanceUploadOut';
import type { ShareAuthStatusOut } from '../models/ShareAuthStatusOut';
import type { TaskCreateIn } from '../models/TaskCreateIn';
import type { TaskCreateOut } from '../models/TaskCreateOut';
import type { TriggerWriteIn } from '../models/TriggerWriteIn';
import type { TriggerWriteOut } from '../models/TriggerWriteOut';
import type { VirtualDisplayDetachOut } from '../models/VirtualDisplayDetachOut';
import type { WebhookTestIn } from '../models/WebhookTestIn';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ActionService {
    /**
     * 从索引全量刷新目录并写入配置（读列表请再调 get）
     * 请求插件管理器重新拉取市场目录，将刷新结果转换为统一接口响应。
     * @param locale
     * @param requestBody
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static refreshPluginCatalogApiPluginCatalogRefreshPost(
        locale: 'zh-CN' | 'en-US' | 'ja-JP' = 'zh-CN',
        requestBody?: PluginCatalogRefreshIn,
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin_catalog/refresh',
            query: {
                'locale': locale,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Prepare Plugin Installation Restart
     * 业务忙时保持等待；空闲后取得重启资格并暂停新任务和插件命令。
     * @param requestBody
     * @param locale
     * @returns PluginInstallationOut Successful Response
     * @throws ApiError
     */
    public static preparePluginInstallationRestartApiPluginInstallationRestartPost(
        requestBody: PluginInstallationRestartIn,
        locale: 'zh-CN' | 'en-US' | 'ja-JP' = 'zh-CN',
    ): CancelablePromise<PluginInstallationOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin/installation/restart',
            query: {
                'locale': locale,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Resume After Plugin Installation Restart
     * 前端未能重启后端时归还资格，候选环境继续保留。
     * @param requestBody
     * @param locale
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static resumeAfterPluginInstallationRestartApiPluginInstallationResumePost(
        requestBody: PluginInstallationRestartIn,
        locale: 'zh-CN' | 'en-US' | 'ja-JP' = 'zh-CN',
    ): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/plugin/installation/resume',
            query: {
                'locale': locale,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Write Config Trigger
     * 写入三态命令并立即返回受影响的任务 UUID。
     * @param requestBody
     * @returns TriggerWriteOut Successful Response
     * @throws ApiError
     */
    public static writeConfigTriggerApiConfigTriggersWritePost(
        requestBody: TriggerWriteIn,
    ): CancelablePromise<TriggerWriteOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/config/triggers/write',
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
     * 分享托管配置到配置中心
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
     * 打开已有 MaaEnd 日志包或保存当前日志
     * @param requestBody
     * @returns MaaEndLogBundleOut Successful Response
     * @throws ApiError
     */
    public static resolveMaaendLogBundleApiScriptsMaaendLogBundlePost(
        requestBody: MaaEndLogBundleIn,
    ): CancelablePromise<MaaEndLogBundleOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/scripts/maaend/log-bundle',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Game
     * @param requestBody
     * @returns GameGetOut Successful Response
     * @throws ApiError
     */
    public static createGameApiGamesCreatePost(
        requestBody: GameCreateIn,
    ): CancelablePromise<GameGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/create',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Search Games
     * @returns GameSearchOut Successful Response
     * @throws ApiError
     */
    public static searchGamesApiGamesSearchPost(): CancelablePromise<GameSearchOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/search',
        });
    }
    /**
     * Import Game
     * @param requestBody
     * @returns GameGetOut Successful Response
     * @throws ApiError
     */
    public static importGameApiGamesImportPost(
        requestBody: GameIdIn,
    ): CancelablePromise<GameGetOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Stable Mode
     * @param requestBody
     * @returns GameSettingsOut Successful Response
     * @throws ApiError
     */
    public static applyStableModeApiGamesStableModeApplyPost(
        requestBody: GameBatchIn,
    ): CancelablePromise<GameSettingsOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/stable-mode/apply',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Capture Baselines
     * @param requestBody
     * @returns GameSettingsOut Successful Response
     * @throws ApiError
     */
    public static captureBaselinesApiGamesGuardCapturePost(
        requestBody: GameBatchIn,
    ): CancelablePromise<GameSettingsOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/games/guard/capture',
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
     * 试存 OBS 回放
     * @returns ObsReplaySaveOut Successful Response
     * @throws ApiError
     */
    public static saveObsReplayApiSettingObsSavePost(): CancelablePromise<ObsReplaySaveOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/obs/save',
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
     * 上传外观包到分享站
     * @param requestBody
     * @returns ShareAppearanceUploadOut Successful Response
     * @throws ApiError
     */
    public static uploadShareAppearanceApiShareAppearanceUploadPost(
        requestBody: ShareAppearanceUploadIn,
    ): CancelablePromise<ShareAppearanceUploadOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/share/appearance/upload',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 修改自己外观的描述
     * @param requestBody
     * @returns ShareAppearanceDescriptionOut Successful Response
     * @throws ApiError
     */
    public static updateMyShareAppearanceDescriptionApiShareAppearanceDescriptionPost(
        requestBody: ShareAppearanceDescriptionIn,
    ): CancelablePromise<ShareAppearanceDescriptionOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/share/appearance/description',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
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
