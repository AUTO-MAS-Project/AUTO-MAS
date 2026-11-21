/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MysteryContextData } from './MysteryContextData';
export type MysteryContextOut = {
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
    data?: (MysteryContextData | null);
    errorCode?: ('DEVICE_UNAVAILABLE' | 'BACKEND_UNAVAILABLE' | null);
};

