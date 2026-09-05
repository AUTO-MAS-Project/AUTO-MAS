/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OpenClawQQQrCheckIn } from '../models/OpenClawQQQrCheckIn';
import type { OpenClawQQQrCheckOut } from '../models/OpenClawQQQrCheckOut';
import type { OpenClawQQQrStartOut } from '../models/OpenClawQQQrStartOut';
import type { OpenClawQQStatusOut } from '../models/OpenClawQQStatusOut';
import type { OutBase } from '../models/OutBase';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class QqService {
    /**
     * 查询 QQ 官方机器人绑定状态
     * 返回 QQ 绑定状态，不返回协议凭据。
     * @returns OpenClawQQStatusOut Successful Response
     * @throws ApiError
     */
    public static getStatusApiSettingOpenclawQqStatusPost(): CancelablePromise<OpenClawQQStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/openclaw-qq/status',
        });
    }
    /**
     * 创建 QQ 官方机器人登录二维码
     * 创建二维码；App ID 和客户端密钥只在后台登录确认后保存。
     * @returns OpenClawQQQrStartOut Successful Response
     * @throws ApiError
     */
    public static startLoginApiSettingOpenclawQqLoginStartPost(): CancelablePromise<OpenClawQQQrStartOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/openclaw-qq/login/start',
        });
    }
    /**
     * 查询 QQ 官方机器人登录状态
     * 轮询二维码状态；确认后自动保存 QQ 机器人凭据。
     * @param requestBody
     * @returns OpenClawQQQrCheckOut Successful Response
     * @throws ApiError
     */
    public static checkLoginApiSettingOpenclawQqLoginCheckPost(
        requestBody: OpenClawQQQrCheckIn,
    ): CancelablePromise<OpenClawQQQrCheckOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/openclaw-qq/login/check',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 解除 QQ 官方机器人绑定
     * 解除绑定并清理本地保存的 QQ 协议状态。
     * @returns OutBase Successful Response
     * @throws ApiError
     */
    public static unbindApiSettingOpenclawQqUnbindPost(): CancelablePromise<OutBase> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/setting/openclaw-qq/unbind',
        });
    }
}
