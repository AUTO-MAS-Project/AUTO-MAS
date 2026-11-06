/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSTaskUserInfoData } from './WSTaskUserInfoData';
/**
 * 任务快照中的托管状态。
 */
export type WSTaskScriptInfoData = {
    /**
     * 托管 ID
     */
    script_id: string;
    /**
     * 托管名称
     */
    name: string;
    /**
     * 托管执行状态
     */
    status: string;
    /**
     * 托管下的账号状态
     */
    userList?: Array<WSTaskUserInfoData>;
};

