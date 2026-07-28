/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type QrCheckOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * Init/Scanned/Confirmed/Error
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 确认后返回的完整 cookie 字符串
     */
    cookies_str?: string;
};

