/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2AffectedScript } from './Emulator2AffectedScript';
export type Emulator2PathRemovePreviewOut = {
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
     * 将会失效的设备号
     */
    slots?: Array<string>;
    /**
     * 受影响的脚本
     */
    affectedScripts?: Array<Emulator2AffectedScript>;
};

