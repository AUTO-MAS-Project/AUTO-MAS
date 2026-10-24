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
     * 是否已开始
     */
    ok?: boolean;
    /**
     * started 已开始 / instances_running 有实例开着 (看 runningInstances) / busy 正在更新 / up_to_date 已是最新 / automas_too_old 要先更新 AUTO-MAS / check_failed 查不到最新版本 / cancelling 正在取消 / not_cancellable 没有可以取消的下载
     */
    reason?: string;
    /**
     * 需要先关的实例台数
     */
    runningInstances?: number;
};

