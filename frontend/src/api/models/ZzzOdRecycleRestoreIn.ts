/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 把回收池里的一条槽快照恢复到该槽号（或指定的其他空闲槽号）
 */
export type ZzzOdRecycleRestoreIn = {
    /**
     * 所属脚本ID
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
     * 恢复到的目标槽号；留空表示恢复回原槽号
     */
    targetSlot?: (number | null);
    /**
     * 目标槽被占用时是否确认覆盖
     */
    force?: boolean;
};

