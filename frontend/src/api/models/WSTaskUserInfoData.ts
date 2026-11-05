/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSTaskUserProgressData } from './WSTaskUserProgressData';
/**
 * 任务快照中的账号状态。
 */
export type WSTaskUserInfoData = {
    /**
     * 账号 ID
     */
    user_id: string;
    /**
     * 账号名称
     */
    name: string;
    /**
     * 账号执行状态
     */
    status: string;
    /**
     * 正在跑的任务进度; 没有任务在跑或该专项不提供时为空
     */
    progress?: (WSTaskUserProgressData | null);
};

