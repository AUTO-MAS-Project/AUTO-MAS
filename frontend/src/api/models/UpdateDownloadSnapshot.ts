/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 更新下载 HTTP 初始快照。
 */
export type UpdateDownloadSnapshot = {
    status?: UpdateDownloadSnapshot.status;
    /**
     * 当前下载版本
     */
    version?: (string | null);
    /**
     * 当前下载源
     */
    source?: (string | null);
    downloaded_size?: number;
    file_size?: number;
    speed?: number;
    /**
     * 完成后的更新包路径
     */
    file?: (string | null);
    /**
     * 失败或状态说明
     */
    message?: (string | null);
};
export namespace UpdateDownloadSnapshot {
    export enum status {
        IDLE = 'idle',
        DOWNLOADING = 'downloading',
        SWITCHING_SOURCE = 'switchingSource',
        COMPLETED = 'completed',
        FAILED = 'failed',
        CANCELLED = 'cancelled',
    }
}

