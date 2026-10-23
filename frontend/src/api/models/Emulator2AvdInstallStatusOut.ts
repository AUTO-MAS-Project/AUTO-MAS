/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Emulator2AvdUpdateProgress } from './Emulator2AvdUpdateProgress';
export type Emulator2AvdInstallStatusOut = {
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
     * 是否正在安装
     */
    busy?: boolean;
    /**
     * 最近一次安装的进度; 补全组件时 message 是脚本最新的一行输出
     */
    progress?: Emulator2AvdUpdateProgress;
};

