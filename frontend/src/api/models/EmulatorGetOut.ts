/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmulatorIndexItem } from './EmulatorIndexItem';
/**
 * 获取模拟器列表响应
 */
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
    index?: Array<EmulatorIndexItem>;
    /**
     * 模拟器数据字典
     */
    data?: Record<string, any>;
};

