/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWShellInstanceItem } from './MaaFWShellInstanceItem';
export type MaaFWShellInstancesOut = {
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
     * 项目目录里找到的外壳配置实例
     */
    data?: Array<MaaFWShellInstanceItem>;
};

