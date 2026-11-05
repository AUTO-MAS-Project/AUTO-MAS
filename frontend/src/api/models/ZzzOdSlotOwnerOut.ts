/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 实例槽的 MAS 归属（哪个脚本的哪个账号占着这个号）
 */
export type ZzzOdSlotOwnerOut = {
    /**
     * 所属托管ID
     */
    scriptId: string;
    /**
     * 账号ID（恢复槽时用它指认目标账号）
     */
    userId: string;
    /**
     * 所属托管名称
     */
    scriptName: string;
    /**
     * 账号名称
     */
    userName: string;
    /**
     * 该账号的 base 来源（shared/independent/native）
     */
    base: string;
};

