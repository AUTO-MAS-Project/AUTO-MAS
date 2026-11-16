/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdUpdateProgress = {
    /**
     * idle / downloading / extracting / verifying / staged (已下载好但这次没换上) / installing / installed / failed
     */
    stage?: string;
    /**
     * running / success / failed / idle
     */
    status?: string;
    /**
     * 当前阶段的用户可读描述
     */
    message?: string;
    /**
     * 当前阶段进度百分比
     */
    percent?: (number | null);
    /**
     * 已处理字节数
     */
    downloadedBytes?: (number | null);
    /**
     * 本阶段总字节数
     */
    totalBytes?: (number | null);
    /**
     * 下载速度 (B/s)
     */
    speedBytesPerSec?: (number | null);
};

