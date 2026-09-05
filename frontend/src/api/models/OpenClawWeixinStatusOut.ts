/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 微信 Claw 通知绑定状态，不返回任何凭据。
 */
export type OpenClawWeixinStatusOut = {
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
     * 是否启用微信 Claw 通知
     */
    enabled?: boolean;
    /**
     * 是否已绑定微信账号
     */
    connected?: boolean;
    /**
     * 当前连接状态
     */
    state?: string;
    /**
     * 是否已取得可用于通知的会话上下文
     */
    contextReady?: boolean;
};

