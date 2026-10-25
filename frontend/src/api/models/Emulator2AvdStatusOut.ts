/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2AvdComponentItem } from './Emulator2AvdComponentItem';
import type { Emulator2AvdPrecheckItem } from './Emulator2AvdPrecheckItem';
export type Emulator2AvdStatusOut = {
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
     * 根目录
     */
    root?: string;
    /**
     * 必需组件是否齐全, 齐了才能添加
     */
    ready?: boolean;
    /**
     * 组件清单
     */
    components?: Array<Emulator2AvdComponentItem>;
    /**
     * 缺着的必需组件名称 (含不合格的模拟器); adb 和系统镜像用包里的「补全组件.bat」补齐
     */
    missing?: Array<string>;
    /**
     * 硬件加速 (WHPX) 是否可用; null 表示还查不了
     */
    accelerationOk?: (boolean | null);
    /**
     * 硬件加速检查结果或不可用的原因与建议
     */
    accelerationDetail?: string;
    /**
     * 开机前电脑检查: 目录路径、组件、模拟器版本、硬件虚拟化、显卡 Vulkan、磁盘、内存 (内存按默认档实例估), 每项给 ok、原因、建议
     */
    prechecks?: Array<Emulator2AvdPrecheckItem>;
};

