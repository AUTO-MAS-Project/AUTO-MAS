/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdInstallCancelOut = {
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
     * 是否已请求取消
     */
    ok?: boolean;
    /**
     * cancelling 正在取消 / no_job 没有在跑的任务
     */
    reason?: string;
};

