/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaEndLogBundleOut = {
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
     * 各安装最新日志包所在目录
     */
    directories?: Array<string>;
    /**
     * 是否需要选择目录保存当前日志
     */
    needsDirectory?: boolean;
    /**
     * 未能保存的文件数
     */
    incompleteCount?: number;
};

