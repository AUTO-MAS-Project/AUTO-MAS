/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Emulator2AvdApkInstallOut = {
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
     * 是否安装成功
     */
    ok?: boolean;
    /**
     * ok 安装成功
     */
    reason?: string;
    /**
     * adb install 的结果行 (Success)
     */
    result?: string;
};

