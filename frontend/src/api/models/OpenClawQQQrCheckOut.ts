/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * QQ 官方机器人二维码及消息网关状态查询响应。
 */
export type OpenClawQQQrCheckOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 二维码登录会话 ID
     */
    sessionId?: string;
    /**
     * 轮询状态：waiting、scanned、connecting（已绑定，网关连接中）、connected（网关已就绪）、expired 或 error
     */
    state?: string;
    /**
     * 消息网关是否已就绪；绑定成功但仍在连接时为 false
     */
    connected?: boolean;
};

