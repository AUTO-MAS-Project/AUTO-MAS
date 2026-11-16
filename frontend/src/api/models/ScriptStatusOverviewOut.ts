/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ScriptStatusOverviewItem } from './ScriptStatusOverviewItem';
export type ScriptStatusOverviewOut = {
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
    data?: Array<ScriptStatusOverviewItem>;
};

