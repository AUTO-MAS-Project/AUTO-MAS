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
     * 已纳管的模拟器路径
     */
    paths?: Array<Emulator2PathItem>;
    /**
     * 合并后的设备列表
     */
    devices?: Array<Emulator2DeviceItem>;
};

