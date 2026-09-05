/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 微信 Claw 二维码创建响应。
 */
export type OpenClawWeixinQrStartOut = {
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
     * 用于生成二维码的登录链接
     */
    qrUrl?: string;
};

