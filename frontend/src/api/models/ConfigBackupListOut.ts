/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConfigBackupItemOut } from './ConfigBackupItemOut';
export type ConfigBackupListOut = {
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
     * 备份列表（时间倒序）
     */
    data: Array<ConfigBackupItemOut>;
    /**
     * 当前配置来源三态（脚本/用户/直控）；非三态专项为 null
     */
    mode?: (string | null);
};

