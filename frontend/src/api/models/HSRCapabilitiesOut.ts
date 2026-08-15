/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRCapabilitiesData } from './HSRCapabilitiesData';
export type HSRCapabilitiesOut = {
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
     * HSR 能力
     */
    data?: (HSRCapabilitiesData | null);
};

