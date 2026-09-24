/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2BatchResult } from './Emulator2BatchResult';
export type Emulator2SettingsApplyAllOut = {
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
     * 逐台结果
     */
    results?: Array<Emulator2BatchResult>;
    /**
     * 成功台数
     */
    okCount?: number;
    /**
     * 失败台数
     */
    failCount?: number;
};

