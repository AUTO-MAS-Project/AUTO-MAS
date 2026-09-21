/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 把回收池里的一条槽快照恢复到该槽号
 */
export type ZzzOdRecycleRestoreIn = {
    /**
     * 所属脚本ID
     */
    scriptId: string;
    /**
     * 目标槽下标
     */
    slot: number;
    /**
     * 快照时间戳
     */
    ts: string;
    /**
     * 目标槽被占用时是否确认覆盖
     */
    force?: boolean;
};

