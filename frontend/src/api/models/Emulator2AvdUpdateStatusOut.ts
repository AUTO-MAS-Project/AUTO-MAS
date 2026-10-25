/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
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
     * 能不能更新
     */
    updatable?: boolean;
    /**
     * 不能更新的原因 (设了 sdkRoot、mas-avd.json 读不出、没有 sdk\emulator)
     */
    notUpdatableReason?: string;
    /**
     * 装着的版本 (有清单读清单, 没有按 Pkg.BuildId=mas-N 算 v0.N.0)
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
     * MAS 要求的最低构建号, 如 mas-25
     */
    minimumBuild?: string;
    /**
     * MAS 要求的最低构建号对应的版本 v0.N.0, 如 v0.25.0 (界面显示时去掉 v)
     */
    minimumVersion?: string;
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
     * 有比装着的新的版本
     */
    updateAvailable?: boolean;
    /**
     * 最新版本要求的 AUTO-MAS 最低版本比当前高时给出; 这时不装, 要先更新 AUTO-MAS
     */
    requiredAutoMas?: string;
    /**
     * 要下载的包的大小 (字节); 不知道时为 0 (Mirror 酱不填 CDK 时不报大小)
     */
    assetSize?: number;
    /**
     * idle / preparing 正在下载、拼新版 / staged 已下载并核对好、等着换上 / swapping 换上中
     */
    phase?: string;
    /**
     * 已下载并核对好、下次点「更新」直接换上的版本
     */
    preparedVersion?: string;
    /**
     * 开着或正在开机的实例台数; 有就不能更新, 要先关掉
     */
    runningInstances?: number;
    /**
     * 正在更新 (这段时间这个根目录不许开机)
     */
    busy?: boolean;
    /**
     * 最近一次更新的进度
     */
    progress?: Emulator2AvdUpdateProgress;
    /**
     * 最近一次换上 / 准备的结果
     */
    lastResult?: (Emulator2AvdUpdateResult | null);
};

