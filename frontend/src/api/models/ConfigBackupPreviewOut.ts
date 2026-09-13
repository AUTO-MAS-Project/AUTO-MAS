/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 备份配置摘要（预览用，纯读不恢复；载荷结构由专项定义）
 */
export type ConfigBackupPreviewOut = {
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
     * 备份时间戳
     */
    time: string;
    /**
     * 备份类别
     */
    target: string;
    /**
     * 专项预览载荷（如 zzz-od 的 info/account/tasks/instances 或 ok-nte 的 files）
     */
    data: Record<string, any>;
};

