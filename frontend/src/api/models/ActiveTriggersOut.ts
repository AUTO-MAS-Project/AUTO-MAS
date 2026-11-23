/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActiveTriggerField } from './ActiveTriggerField';
export type ActiveTriggersOut = {
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
    uiSources?: Array<string>;
    data?: Array<ActiveTriggerField>;
};

