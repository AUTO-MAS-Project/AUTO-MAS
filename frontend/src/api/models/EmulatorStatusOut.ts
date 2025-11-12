/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DeviceInfo } from './DeviceInfo';
export type EmulatorStatusOut = {
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
     * 模拟器状态信息, 外层key为模拟器ID, 内层key为设备索引, value为设备信息
     */
    data: Record<string, Record<string, DeviceInfo>>;
};

