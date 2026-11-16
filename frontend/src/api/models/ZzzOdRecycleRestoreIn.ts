/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 把回收池里的一条槽快照恢复给某个 MAS 账号（现有用户或新建账号）
 */
export type ZzzOdRecycleRestoreIn = {
    /**
     * 所属托管ID
     */
    scriptId: string;
    /**
     * 快照所属槽下标（回收条目的槽号）
     */
    slot: number;
    /**
     * 快照时间戳
     */
    ts: string;
    /**
     * 恢复给该账号的绑定槽（现有账号 uid）
     */
    targetUser?: (string | null);
    /**
     * 新建一个账号并把内容恢复到它的槽（账号名称）
     */
    newUserName?: (string | null);
};

