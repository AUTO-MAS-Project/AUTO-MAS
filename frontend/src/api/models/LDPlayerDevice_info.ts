/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DeviceStatus } from './DeviceStatus';
export type LDPlayerDevice_info = {
    /**
     * 实例名称
     */
    readonly name?: (string | null);
    /**
     * 实例状态
     */
    readonly status?: (DeviceStatus | null);
    /**
     * 多开序号
     */
    readonly index?: (string | null);
    /**
     * ADB 连接地址
     */
    readonly adb_address?: (string | null);
    /**
     * 稳定显示槽位，删除后不复用
     */
    readonly slot?: (number | null);
    /**
     * 实例已删除，保留身份与恢复材料
     */
    readonly tombstone?: (boolean | null);
};

