/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdSourceItem = {
    /**
     * 下载源标识
     */
    id: string;
    /**
     * 下载源名称
     */
    name: string;
    /**
     * 仓库根地址
     */
    url: string;
    /**
     * 测速是否成功
     */
    ok?: boolean;
    /**
     * 测得的速度 (B/s), 失败时为 null
     */
    speedBytesPerSec?: (number | null);
    /**
     * 失败原因
     */
    error?: string;
};

