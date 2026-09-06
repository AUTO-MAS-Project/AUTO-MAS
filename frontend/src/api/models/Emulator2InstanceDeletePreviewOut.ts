/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2AffectedScript } from './Emulator2AffectedScript';
export type Emulator2InstanceDeletePreviewOut = {
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
     * 设备号是否有效
     */
    ok?: boolean;
    /**
     * 失败原因枚举
     */
    reason?: string;
    /**
     * 绑定了该设备号的脚本
     */
    affectedScripts?: Array<Emulator2AffectedScript>;
};

