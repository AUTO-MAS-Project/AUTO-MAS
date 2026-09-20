/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PushLogPattern } from './PushLogPattern';
/**
 * 日志模式调试请求
 */
export type PatternDebugIn = {
    /**
     * 待调试的推送日志模式配置
     */
    pattern: PushLogPattern;
    /**
     * 待调试的多行日志文本
     */
    logText?: string;
};

