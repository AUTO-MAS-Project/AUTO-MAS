/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ConfigBackupEnsureOut = {
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
     * 本次是否新建了归档（False=指纹无变化跳过或无可归档内容）
     */
    created: boolean;
    /**
     * 最新备份时间戳（无任何备份为空串）
     */
    time: string;
};

