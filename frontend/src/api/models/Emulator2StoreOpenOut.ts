/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2StoreOpenOut = {
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
     * 游戏中心是否已在前台
     */
    ok?: boolean;
    /**
     * 结局原因码: launched / already-running / no-store / not-installed / no-adb / boot-timeout / launch-timeout
     */
    reason?: string;
};

