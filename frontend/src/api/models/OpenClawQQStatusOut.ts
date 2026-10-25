/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * QQ 官方机器人通知绑定状态，不返回任何凭据。
 */
export type OpenClawQQStatusOut = {
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
     * 是否启用 QQ 官方机器人通知
     */
    enabled?: boolean;
    /**
     * 是否已绑定 QQ 官方机器人
     */
    connected?: boolean;
    /**
     * 消息网关状态：disconnected、connecting、connected 或 reconnecting
     */
    state?: string;
};

