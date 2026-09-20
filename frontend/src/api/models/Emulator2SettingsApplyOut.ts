/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2SettingsApplyOut = {
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
     * 是否写入成功
     */
    ok?: boolean;
    /**
     * 编辑期间被改动的字段名
     */
    conflicts?: Array<string>;
    /**
     * 真正落盘的字段
     */
    applied?: Record<string, number>;
};

