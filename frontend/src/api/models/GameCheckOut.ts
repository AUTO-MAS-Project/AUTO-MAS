/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type GameCheckOut = {
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
     * 本地已装版本
     */
    local_version?: string;
    /**
     * 最新版本
     */
    latest_version?: string;
    /**
     * 是否有更新
     */
    needs_update?: boolean;
    /**
     * 是否已安装
     */
    installed?: boolean;
};

