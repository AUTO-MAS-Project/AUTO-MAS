/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OpenClawWeixinQrCheckIn } from '../models/OpenClawWeixinQrCheckIn';
import type { OpenClawWeixinQrCheckOut } from '../models/OpenClawWeixinQrCheckOut';
import type { OpenClawWeixinQrStartOut } from '../models/OpenClawWeixinQrStartOut';
import type { OpenClawWeixinStatusOut } from '../models/OpenClawWeixinStatusOut';
import type { OutBase } from '../models/OutBase';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ClawService {
    /**
     * 查询微信 Claw 绑定状态
     * 返回微信绑定状态，不返回协议凭据。
     * @returns OpenClawWeixinStatusOut Successful Response
     * @throws ApiError
     */
    public static getStatusApiSettingOpenclawWeixinStatusPost(): CancelablePromise<OpenClawWeixinStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/openclaw-weixin/status',
        });
    }
    /**
     * 创建微信 Claw 登录二维码
     * 创建二维码；Bot Token 等凭据只在后台登录确认后保存。
     * @returns OpenClawWeixinQrStartOut Successful Response
     * @throws ApiError
     */
    public static startLoginApiSettingOpenclawWeixinLoginStartPost(): CancelablePromise<OpenClawWeixinQrStartOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/openclaw-weixin/login/start',
        });
    }
    /**
     * 查询微信 Claw 登录状态
     * 查询二维码状态；确认后自动保存账号并启动上下文轮询。
     * @param requestBody
     * @returns OpenClawWeixinQrCheckOut Successful Response
     * @throws ApiError
     */
    public static checkLoginApiSettingOpenclawWeixinLoginCheckPost(
        requestBody: OpenClawWeixinQrCheckIn,
    ): CancelablePromise<OpenClawWeixinQrCheckOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/openclaw-weixin/login/check',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 解除微信 Claw 绑定
     * 解除绑定并清理本地保存的微信协议状态。
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static unbindApiSettingOpenclawWeixinUnbindPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/openclaw-weixin/unbind',
        });
    }
}
