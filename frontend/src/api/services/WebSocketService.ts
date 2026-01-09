/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSClearHistoryIn } from '../models/WSClearHistoryIn';
import type { WSClientAuthIn } from '../models/WSClientAuthIn';
import type { WSClientConnectIn } from '../models/WSClientConnectIn';
import type { WSClientCreateIn } from '../models/WSClientCreateIn';
import type { WSClientCreateOut } from '../models/WSClientCreateOut';
import type { WSClientDisconnectIn } from '../models/WSClientDisconnectIn';
import type { WSClientListOut } from '../models/WSClientListOut';
import type { WSClientRemoveIn } from '../models/WSClientRemoveIn';
import type { WSClientSendIn } from '../models/WSClientSendIn';
import type { WSClientSendJsonIn } from '../models/WSClientSendJsonIn';
import type { WSClientStatusIn } from '../models/WSClientStatusIn';
import type { WSClientStatusOut } from '../models/WSClientStatusOut';
import type { WSCommandsOut } from '../models/WSCommandsOut';
import type { WSMessageHistoryOut } from '../models/WSMessageHistoryOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class WebSocketService {
    /**
     * 创建 WebSocket 客户端
     * 创建一个新的 WebSocket 客户端实例
     *
     * - **name**: 客户端唯一名称
     * - **url**: WebSocket 服务器地址
     * - **ping_interval**: 心跳发送间隔
     * - **ping_timeout**: 心跳超时时间
     * - **reconnect_interval**: 重连间隔
     * - **max_reconnect_attempts**: 最大重连次数
     * @param requestBody
     * @returns WSClientCreateOut Successful Response
     * @throws ApiError
     */
    public static createClientApiWsDebugClientCreatePost(
        requestBody: WSClientCreateIn,
    ): CancelablePromise<WSClientCreateOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ws_debug/client/create',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 连接 WebSocket 客户端
     * 启动指定客户端的连接（非阻塞）
     * @param requestBody
     * @returns WSClientStatusOut Successful Response
     * @throws ApiError
     */
    public static connectClientApiWsDebugClientConnectPost(
        requestBody: WSClientConnectIn,
    ): CancelablePromise<WSClientStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ws_debug/client/connect',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 断开 WebSocket 客户端
     * 断开指定客户端的连接
     * @param requestBody
     * @returns WSClientStatusOut Successful Response
     * @throws ApiError
     */
    public static disconnectClientApiWsDebugClientDisconnectPost(
        requestBody: WSClientDisconnectIn,
    ): CancelablePromise<WSClientStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ws_debug/client/disconnect',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 删除 WebSocket 客户端
     * 删除指定客户端（会自动断开连接）
     *
     * 注意：系统客户端（如 Koishi）不可删除
     * @param requestBody
     * @returns WSClientStatusOut Successful Response
     * @throws ApiError
     */
    public static removeClientApiWsDebugClientRemovePost(
        requestBody: WSClientRemoveIn,
    ): CancelablePromise<WSClientStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ws_debug/client/remove',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取客户端状态
     * 获取指定客户端的状态信息
     * @param requestBody
     * @returns WSClientStatusOut Successful Response
     * @throws ApiError
     */
    public static getClientStatusApiWsDebugClientStatusPost(
        requestBody: WSClientStatusIn,
    ): CancelablePromise<WSClientStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ws_debug/client/status',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 列出所有客户端
     * 获取所有已创建的 WebSocket 客户端列表及状态
     * @returns WSClientListOut Successful Response
     * @throws ApiError
     */
    public static listClientsApiWsDebugClientListGet(): CancelablePromise<WSClientListOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/ws_debug/client/list',
        });
    }
    /**
     * 发送原始消息
     * 发送原始 JSON 消息到指定客户端连接的服务器
     * @param requestBody
     * @returns WSClientStatusOut Successful Response
     * @throws ApiError
     */
    public static sendMessageApiWsDebugMessageSendPost(
        requestBody: WSClientSendIn,
    ): CancelablePromise<WSClientStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ws_debug/message/send',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 发送格式化消息
     * 发送格式化的 JSON 消息（自动组装 id、type、data 结构）
     * @param requestBody
     * @returns WSClientStatusOut Successful Response
     * @throws ApiError
     */
    public static sendJsonMessageApiWsDebugMessageSendJsonPost(
        requestBody: WSClientSendJsonIn,
    ): CancelablePromise<WSClientStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ws_debug/message/send_json',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 发送认证消息
     * 发送认证消息到服务器
     *
     * - **name**: 客户端名称
     * - **token**: 认证 Token
     * - **auth_type**: 认证消息类型，默认 "auth"
     * - **extra_data**: 额外的认证数据
     * @param requestBody
     * @returns WSClientStatusOut Successful Response
     * @throws ApiError
     */
    public static sendAuthApiWsDebugMessageAuthPost(
        requestBody: WSClientAuthIn,
    ): CancelablePromise<WSClientStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ws_debug/message/auth',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取消息历史
     * 获取消息历史记录
     *
     * - **name**: 客户端名称，为空则获取所有客户端的历史
     * @param name
     * @returns WSMessageHistoryOut Successful Response
     * @throws ApiError
     */
    public static getHistoryApiWsDebugHistoryGet(
        name?: (string | null),
    ): CancelablePromise<WSMessageHistoryOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/ws_debug/history',
            query: {
                'name': name,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 清空消息历史
     * 清空消息历史记录
     *
     * - **name**: 客户端名称，为空则清空所有
     * @param requestBody
     * @returns WSClientStatusOut Successful Response
     * @throws ApiError
     */
    public static clearHistoryApiWsDebugHistoryClearPost(
        requestBody: WSClearHistoryIn,
    ): CancelablePromise<WSClientStatusOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ws_debug/history/clear',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 获取可用 WS 命令
     * 获取所有已注册的 WebSocket 命令端点
     * @returns WSCommandsOut Successful Response
     * @throws ApiError
     */
    public static getCommandsApiWsDebugCommandsGet(): CancelablePromise<WSCommandsOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/ws_debug/commands',
        });
    }
}
