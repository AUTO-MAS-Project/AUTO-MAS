/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type VersionOut = {
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
     * 后端代码是否为最新
     */
    if_latest: boolean;
    /**
     * 后端代码当前哈希值
     */
    current_hash: string;
    /**
     * 后端代码当前时间戳
     */
    current_time: string;
    /**
     * 后端当前版本号
     */
    current_version: string;
};

