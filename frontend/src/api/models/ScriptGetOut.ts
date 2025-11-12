/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralConfig } from './GeneralConfig';
import type { MaaConfig } from './MaaConfig';
import type { ScriptIndexItem } from './ScriptIndexItem';
export type ScriptGetOut = {
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
     * 脚本索引列表
     */
    index: Array<ScriptIndexItem>;
    /**
     * 脚本数据字典, key来自于index列表的uid
     */
    data: Record<string, (MaaConfig | GeneralConfig)>;
};

