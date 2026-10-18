/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWGamePackageData } from './MaaFWGamePackageData';
export type MaaFWGamePackageOut = {
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
     * 包名推断结果
     */
    data?: (MaaFWGamePackageData | null);
};

