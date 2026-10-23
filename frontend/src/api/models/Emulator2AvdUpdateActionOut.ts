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
     * started 已开始 / instances_running 有实例开着 (看 runningInstances) / instances_booting 有实例正在开机 / tasks_running 有任务在跑 (手动安装 / 回退要等任务都结束) / busy 正在下载或安装 / not_prepared 还没下载好 / no_previous 没有旧版或旧版不完整
     */
    reason?: string;
    /**
     * 需要先关的实例台数
     */
    runningInstances?: number;
};

