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
     * Init/Scanned/Confirmed/Expired/Canceled/Error
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 稳定错误码，前端据此取当前界面语言的文案
     */
    errorCode?: (string | null);
    /**
     * 错误码文案里的占位符参数
     */
    errorParams?: (Record<string, any> | null);
    /**
     * 确认后返回的完整 cookie 字符串
     */
    cookies_str?: string;
};

