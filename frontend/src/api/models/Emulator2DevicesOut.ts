/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2DeviceItem } from './Emulator2DeviceItem';
import type { Emulator2PathItem } from './Emulator2PathItem';
export type Emulator2DevicesOut = {
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
     * 稳定错误码，前端据此取当前界面语言的文案
     */
    errorCode?: (string | null);
    /**
     * 错误码文案里的占位符参数
     */
    errorParams?: (Record<string, any> | null);
    /**
     * 已纳管的模拟器路径
     */
    paths?: Array<Emulator2PathItem>;
    /**
     * 合并后的设备列表
     */
    devices?: Array<Emulator2DeviceItem>;
};

