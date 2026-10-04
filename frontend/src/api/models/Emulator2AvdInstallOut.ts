/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSEmulator2AvdInstallProgressData } from './WSEmulator2AvdInstallProgressData';
export type Emulator2AvdInstallOut = {
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
     * 是否已开始 (或已有同目录任务在跑)
     */
    ok?: boolean;
    /**
     * 结果原因: started 已开始 / running 已有任务在跑 / ready 组件已齐无需下载 / license_not_accepted 未同意许可协议 / invalid_root 目录不可用 / disk_space 磁盘空间不足 / no_source 所有下载源都不可用
     */
    reason?: string;
    /**
     * 下载任务 ID
     */
    jobId?: string;
    /**
     * 当前进度快照
     */
    job?: (WSEmulator2AvdInstallProgressData | null);
};

