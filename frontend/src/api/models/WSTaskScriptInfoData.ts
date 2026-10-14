/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSTaskUserInfoData } from './WSTaskUserInfoData';
/**
 * 任务快照中的脚本状态。
 */
export type WSTaskScriptInfoData = {
    /**
     * 脚本 ID
     */
    script_id: string;
    /**
     * 脚本名称
     */
    name: string;
    /**
     * 脚本执行状态
     */
    status: string;
    /**
     * 脚本下的用户状态
     */
    userList?: Array<WSTaskUserInfoData>;
};

