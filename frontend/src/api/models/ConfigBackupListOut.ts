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
     * 当前 base 来源（shared/independent/native）；无来源概念（非 base 专项）为 null
     */
    base?: (string | null);
};

