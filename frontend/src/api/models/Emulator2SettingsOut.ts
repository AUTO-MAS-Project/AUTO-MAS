/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2SettingField } from './Emulator2SettingField';
export type Emulator2SettingsOut = {
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
     * 设备号
     */
    slot?: string;
    /**
     * 四项设置的当前值与状态
     */
    settings?: Record<string, Emulator2SettingField>;
};

