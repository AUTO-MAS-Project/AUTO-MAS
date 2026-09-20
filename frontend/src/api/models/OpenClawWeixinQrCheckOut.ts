/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 微信 Claw 二维码状态查询响应。
 */
export type OpenClawWeixinQrCheckOut = {
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
     * 二维码状态
     */
    state?: string;
    /**
     * 是否已完成账号绑定
     */
    connected?: boolean;
};

