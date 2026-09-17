/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 备份内文本文件内容（只读；路径限归档内相对路径，防穿越）
 */
export type ConfigBackupFileOut = {
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
     * 备份时间戳
     */
    time: string;
    /**
     * 备份类别
     */
    target: string;
    /**
     * 归档内相对路径（如 M7A/config.yaml）
     */
    path: string;
    /**
     * 文件字节数
     */
    size: number;
    /**
     * 文本内容（utf-8 读取；超出大小上限返回 400）
     */
    content: string;
};

