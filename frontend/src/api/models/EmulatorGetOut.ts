/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmulatorConfig } from './EmulatorConfig';
import type { EmulatorConfigIndexItem } from './EmulatorConfigIndexItem';
export type EmulatorGetOut = {
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
     * 模拟器索引列表
     */
    index: Array<EmulatorConfigIndexItem>;
    /**
     * 模拟器数据字典, key来自于index列表的uid
     */
    data: Record<string, EmulatorConfig>;
};

