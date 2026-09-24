/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkScriptProjectInfo } from './OkScriptProjectInfo';
export type OkScriptProbeOut = {
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
     * 识别结果，识别失败时为空
     */
    data?: (OkScriptProjectInfo | null);
};

