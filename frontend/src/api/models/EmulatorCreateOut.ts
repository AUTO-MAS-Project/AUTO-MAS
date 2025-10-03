/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmulatorInfo } from './EmulatorInfo';
/**
 * 创建模拟器配置响应
 */
export type EmulatorCreateOut = {
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
     * 新创建的模拟器ID
     */
    emulatorId: string;
    /**
     * 模拟器配置数据
     */
    data: EmulatorInfo;
};

