/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 库街区短信发送响应。
 */
export type KuroSmsSendOut = {
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
     * 短期短信登录会话标识
     */
    sessionId?: string;
    /**
     * 会话剩余秒数
     */
    expiresIn?: number;
};
