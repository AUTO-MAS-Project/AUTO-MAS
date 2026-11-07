/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PowerSignal } from './PowerSignal';
export type TaskItem_execution = {
    /**
     * 本轮运行前脚本
     */
    script_before?: (string | null);
    /**
     * 本轮运行后脚本
     */
    script_after?: (string | null);
    /**
     * 本轮完成后操作
     */
    after_accomplish?: (PowerSignal | null);
    /**
     * 完成后操作倒计时，单位分钟
     */
    after_accomplish_delay?: (number | null);
};
