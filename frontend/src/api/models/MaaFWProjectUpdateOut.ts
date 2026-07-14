/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWProjectUpdateData } from './MaaFWProjectUpdateData';
export type MaaFWProjectUpdateOut = {
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
     * MaaFW 项目更新结果
     */
    data?: (MaaFWProjectUpdateData | null);
};

