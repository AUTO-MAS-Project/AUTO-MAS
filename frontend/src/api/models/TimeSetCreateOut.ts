/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TimeSetEntry_Output } from './TimeSetEntry_Output';
export type TimeSetCreateOut = {
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
     * 新定时项 ID
     */
    timeSetId?: string;
    /**
     * 定时项配置
     */
    data?: TimeSetEntry_Output;
};

