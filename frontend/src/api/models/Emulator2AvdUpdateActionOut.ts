/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdUpdateActionOut = {
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
     * 是否已开始
     */
    ok?: boolean;
    /**
     * started 已开始 / instances_running 有实例开着或正在开机, 什么都没动, 要先关掉 (看 runningInstances) / busy 正在更新 / up_to_date 已是最新 / automas_too_old 要先更新 AUTO-MAS / check_failed 查不到最新版本
     */
    reason?: string;
    /**
     * 开着或正在开机、要先关掉的实例台数
     */
    runningInstances?: number;
};

