/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 实例槽的 MAS 归属（哪个脚本的哪个用户占着这个号）
 */
export type ZzzOdSlotOwnerOut = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 用户ID（恢复槽时用它指认目标用户）
     */
    userId: string;
    /**
     * 所属脚本名称
     */
    scriptName: string;
    /**
     * 用户名称
     */
    userName: string;
    /**
     * 该用户的配置来源（脚本/用户/直控）
     */
    mode: string;
};

