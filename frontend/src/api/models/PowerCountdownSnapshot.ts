/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PowerSignal } from './PowerSignal';
/**
 * 当前电源倒计时 HTTP 初始快照。
 */
export type PowerCountdownSnapshot = {
    /**
     * 是否正在倒计时
     */
    active?: boolean;
    /**
     * 待执行电源操作
     */
    operation?: (PowerSignal | null);
    /**
     * 剩余秒数
     */
    remaining?: number;
};

