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
    compatible: boolean;
    conflicts?: Array<CoreUpgradeConflict>;
};

