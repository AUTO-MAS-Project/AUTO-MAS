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
     * 稳定错误码，前端据此取当前界面语言的文案
     */
    errorCode?: (string | null);
    /**
     * 错误码文案里的占位符参数
     */
    errorParams?: (Record<string, any> | null);
    /**
     * 本次是否新建了归档（False=指纹无变化跳过或无可归档内容）
     */
    created: boolean;
    /**
     * 最新备份时间戳（无任何备份为空串）
     */
    time: string;
};

