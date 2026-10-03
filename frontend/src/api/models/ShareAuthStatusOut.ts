/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ShareAuthStatusOut = {
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
     * 配置中心授权状态
     */
    authStatus: ShareAuthStatusOut.authStatus;
    /**
     * 已授权用户的用户名
     */
    username?: string;
    /**
     * 已授权用户的显示名
     */
    displayName?: string;
    /**
     * 待用户在浏览器确认的短授权码
     */
    userCode?: string;
    /**
     * 浏览器授权页地址
     */
    verificationUri?: string;
    /**
     * 剩余有效秒数
     */
    expiresIn?: number;
    /**
     * 建议的轮询间隔秒数
     */
    interval?: number;
};
export namespace ShareAuthStatusOut {
    /**
     * 配置中心授权状态
     */
    export enum authStatus {
        IDLE = 'idle',
        PENDING = 'pending',
        AUTHORIZED = 'authorized',
        DENIED = 'denied',
        EXPIRED = 'expired',
    }
}

