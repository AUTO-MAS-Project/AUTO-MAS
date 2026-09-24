/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SklandQrCreateOut = {
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
     * 森空岛扫码 ticket/scanId
     */
    ticket?: string;
    /**
     * 用于生成二维码的跳转链接
     */
    qr_url?: string;
    /**
     * 本地设备 ID
     */
    device?: string;
};

