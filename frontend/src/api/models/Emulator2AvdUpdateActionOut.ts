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
     * 是否已开始 (或已办成)
     */
    ok?: boolean;
    /**
     * started 已开始 / instances_running 有实例开着 (看 runningInstances) / tasks_running 有任务在跑 / busy 正在下载或安装 / not_prepared 还没下载好 / no_previous 没有旧版可回退
     */
    reason?: string;
    /**
     * 需要先关的实例台数
     */
    runningInstances?: number;
};

