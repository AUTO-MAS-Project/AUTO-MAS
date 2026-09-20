/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SklandQrCheckOut = {
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
     * 确认后返回的短时 scanCode
     */
    scan_code?: string;
};

