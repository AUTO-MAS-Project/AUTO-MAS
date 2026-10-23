/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2AvdChangeEntry } from './Emulator2AvdChangeEntry';
import type { Emulator2AvdUpdateProgress } from './Emulator2AvdUpdateProgress';
import type { Emulator2AvdUpdateResult } from './Emulator2AvdUpdateResult';
export type Emulator2AvdUpdateStatusOut = {
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
     * 能不能更新
     */
    updatable?: boolean;
    /**
     * 不能更新的原因 (设了 sdkRoot、没有 sdk\emulator)
     */
    notUpdatableReason?: string;
    /**
     * 装着的版本 (有清单读清单, 没有按 Pkg.BuildId 算 vN.0.0)
     */
    currentVersion?: string;
    /**
     * 装着的构建号, 如 mas-32
     */
    currentBuild?: string;
    /**
     * 装着的低于 MAS 要求的最低构建号, 开机前检查会拒绝开机
     */
    belowMinimum?: boolean;
    /**
     * MAS 要求的最低构建号
     */
    minimumBuild?: string;
    /**
     * 上次查更新的时间; 没查过为 null
     */
    checkedAt?: (string | null);
    /**
     * 上次查更新失败的原因
     */
    checkError?: string;
    /**
     * 最新版本号; 没查到为空
     */
    latestVersion?: string;
    /**
     * 最新构建号
     */
    latestBuild?: string;
    /**
     * 最新版本的 Release 标题
     */
    latestTitle?: string;
    /**
     * 最新版本的 Release 页面
     */
    releaseUrl?: string;
    /**
     * 有比装着的新的版本
     */
    updateAvailable?: boolean;
    /**
     * 最新版本要求的 AUTO-MAS 最低版本比当前高时给出; 这时不装, 要先更新 AUTO-MAS
     */
    requiredAutoMas?: string;
    /**
     * 最新版本的更新公告 (Markdown, 只含分隔行以上)
     */
    announcement?: string;
    /**
     * 比装着的新的各版摘要 (跳版本时合起来), 从新到旧
     */
    changes?: Array<Emulator2AvdChangeEntry>;
    /**
     * 要下载的包
     */
    assetName?: string;
    /**
     * 包的大小 (字节)
     */
    assetSize?: number;
    /**
     * idle / preparing 正在下载、拼新版 (不可安装) / staged 已拼好、核对过、可安装 / swapping 换上中 / rolling_back 回退中
     */
    phase?: string;
    /**
     * 已下载并核对、等着安装的版本
     */
    preparedVersion?: string;
    /**
     * 开着的实例台数 (安装前要先关掉)
     */
    runningInstances?: number;
    /**
     * 没有实例开着、却还有程序在用 sdk\emulator 里的文件时列出来 (要用户自己关)
     */
    busyProcesses?: Array<string>;
    /**
     * 能不能回到上一版
     */
    canRollback?: boolean;
    /**
     * 上一版的版本号
     */
    previousVersion?: string;
    /**
     * 刚换上的新版还没开过机 (开机成功后删旧版)
     */
    awaitingBoot?: boolean;
    /**
     * 空闲时自动装
     */
    autoInstall?: boolean;
    /**
     * 正在下载 / 安装 / 回退
     */
    busy?: boolean;
    /**
     * 最近一次操作的进度
     */
    progress?: Emulator2AvdUpdateProgress;
    /**
     * 最近一次换上 / 回退 / 开机确认的结果
     */
    lastResult?: (Emulator2AvdUpdateResult | null);
};

