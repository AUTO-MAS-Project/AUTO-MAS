/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmulatorConfig } from './EmulatorConfig';
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
     * 新创建的模拟器 ID
     */
    emulatorId: string;
    /**
     * 模拟器配置数据
     */
    data: EmulatorConfig;
};

