/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * FluxDown 最新 Release 的直链信息，供设置页展示。
 */
export type FluxdownReleaseOut = {
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
     * 版本号（不含 v 前缀）
     */
    version?: string;
    /**
     * Release tag
     */
    tag?: string;
    /**
     * CLI 包 GitHub 直链
     */
    cli_url?: string;
    /**
     * Server 包 GitHub 直链
     */
    server_url?: string;
    /**
     * GitHub Release 页面
     */
    release_page?: string;
    /**
     * 可用下载镜像标识，按推荐顺序
     */
    mirrors?: Array<string>;
};
