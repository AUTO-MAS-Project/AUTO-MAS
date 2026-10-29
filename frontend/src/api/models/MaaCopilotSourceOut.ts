/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaCopilotSourceOut = {
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
    running?: boolean;
    loaded?: number;
    total?: number;
    count?: number;
    /**
     * 作业数据或快照的生成时间，Unix 秒
     */
    updatedAt?: number;
    /**
     * 本机下载或在线同步完成时间，Unix 秒
     */
    downloadedAt?: number;
    dataSource?: MaaCopilotSourceOut.dataSource;
    available?: boolean;
    error?: string;
};
export namespace MaaCopilotSourceOut {
    export enum dataSource {
        DATA_CENTER = 'data-center',
        GITHUB = 'github',
        COPILOT = 'copilot',
        UNKNOWN = 'unknown',
    }
}

