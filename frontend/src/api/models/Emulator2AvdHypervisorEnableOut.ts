/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdHypervisorEnableOut = {
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
     * 是否已开启 (要重启电脑才生效)
     */
    ok?: boolean;
    /**
     * enabled 已开启, 要重启 / cancelled 用户在系统确认框里取消 / failed 失败 / running 上一次还没结束
     */
    reason?: string;
    /**
     * 是否要重启电脑才生效
     */
    restartRequired?: boolean;
    /**
     * dism 的退出码 (0 / 3010 为成功)
     */
    exitCode?: (number | null);
};

