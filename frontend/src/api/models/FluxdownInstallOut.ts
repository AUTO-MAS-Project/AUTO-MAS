/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * MAS 代为下载并安装 FluxDown 的结果。
 */
export type FluxdownInstallOut = {
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
     * 已安装版本
     */
    version?: string;
    /**
     * 安装目录，已写入 Update.FluxdownPath
     */
    path?: string;
    /**
     * CLI 包字节数
     */
    cli_size?: number;
    /**
     * Server 包字节数
     */
    server_size?: number;
};
