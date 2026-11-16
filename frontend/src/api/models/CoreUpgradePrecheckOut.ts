/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CoreUpgradeConflict } from './CoreUpgradeConflict';
export type CoreUpgradePrecheckOut = {
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
     * true 表示兼容，false 表示依赖无解，null 表示检查未完成
     */
    compatible: (boolean | null);
    conflicts?: Array<CoreUpgradeConflict>;
};

