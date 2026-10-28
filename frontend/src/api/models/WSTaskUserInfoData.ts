/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSTaskUserProgressData } from './WSTaskUserProgressData';
/**
 * 任务快照中的用户状态。
 */
export type WSTaskUserInfoData = {
    /**
     * 用户 ID
     */
    user_id: string;
    /**
     * 用户名称
     */
    name: string;
    /**
     * 用户执行状态
     */
    status: string;
    /**
     * 正在跑的任务进度; 没有任务在跑或该专项不提供时为空
     */
    progress?: (WSTaskUserProgressData | null);
};

