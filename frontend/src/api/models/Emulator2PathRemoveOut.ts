/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2AffectedScript } from './Emulator2AffectedScript';
export type Emulator2PathRemoveOut = {
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
     * 是否移除成功
     */
    ok?: boolean;
    /**
     * 已失效并保留的设备号, 不会再分配给其他设备
     */
    tombstonedSlots?: Array<string>;
    /**
     * 受影响的脚本
     */
    affectedScripts?: Array<Emulator2AffectedScript>;
};

