/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2AvdComponentItem } from './Emulator2AvdComponentItem';
import type { Emulator2AvdPrecheckItem } from './Emulator2AvdPrecheckItem';
import type { WSEmulator2AvdInstallProgressData } from './WSEmulator2AvdInstallProgressData';
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
     * 根目录
     */
    root?: string;
    /**
     * 必需组件是否齐全, 齐了才能添加
     */
    ready?: boolean;
    /**
     * 组件清单 (含可选的轻量桌面)
     */
    components?: Array<Emulator2AvdComponentItem>;
    /**
     * 还要下载的字节数
     */
    missingBytes?: number;
    /**
     * 下载并解压还需要的磁盘空间 (字节, 不含余量)
     */
    requiredDiskBytes?: number;
    /**
     * 根目录所在盘的剩余空间 (字节)
     */
    freeDiskBytes?: (number | null);
    /**
     * 该根目录是否已同意过许可协议
     */
    licenseAccepted?: boolean;
    /**
     * 同意许可协议的时间
     */
    licenseAcceptedAt?: string;
    /**
     * 上次使用的下载源标识
     */
    source?: string;
    /**
     * 硬件加速 (WHPX) 是否可用; 模拟器组件还没装时为 null (无法检查)
     */
    accelerationOk?: (boolean | null);
    /**
     * 硬件加速检查的原始输出或不可用时的引导文案
     */
    accelerationDetail?: string;
    /**
     * 开机前电脑检查: 硬件虚拟化、显卡 Vulkan、磁盘、内存 (内存按默认档实例估), 每项给 ok、原因、建议
     */
    prechecks?: Array<Emulator2AvdPrecheckItem>;
    /**
     * 该根目录最近一次下载任务的进度快照, 没有时为 null
     */
    job?: (WSEmulator2AvdInstallProgressData | null);
};

