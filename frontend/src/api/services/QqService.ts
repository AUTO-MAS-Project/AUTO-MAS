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
     * 返回 QQ 绑定及网关状态，不返回协议凭据。
     *
     * connected 表示凭据已绑定；state 表示网关是连接中、已连接还是重连中。
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
     * 轮询二维码与消息网关状态。
     *
     * 扫码确认后先保存凭据，此时可能返回 state=connecting、connected=false；
     * 网关 READY 后返回 state=connected、connected=true。网关等待超时
     * 返回 state=error，但绑定凭据仍保留，后台继续重连。
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
