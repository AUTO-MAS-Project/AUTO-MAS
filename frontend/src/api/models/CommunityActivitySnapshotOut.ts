/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CommunityActivityResourceOut } from './CommunityActivityResourceOut';
import type { CommunityActivityTaskOut } from './CommunityActivityTaskOut';
/**
 * 单个游戏角色的日常活动快照。
 */
export type CommunityActivitySnapshotOut = {
    /**
     * 账号组名称
     */
    account: string;
    /**
     * 账号组 UUID
     */
    accountUid: string;
    /**
     * 游戏名称
     */
    game: string;
    /**
     * 社区平台名称
     */
    platform: string;
    /**
     * 活动查询状态
     */
    status: CommunityActivitySnapshotOut.status;
    /**
     * 已完成数量
     */
    completed?: (number | null);
    /**
     * 目标数量
     */
    target?: (number | null);
    /**
     * 每日任务
     */
    tasks?: Array<CommunityActivityTaskOut>;
    /**
     * 可用资源
     */
    resources?: Array<CommunityActivityResourceOut>;
    /**
     * 失败或受限原因
     */
    reason?: string;
    /**
     * 查询时间
     */
    updatedAt?: string;
    /**
     * 角色名称
     */
    roleName?: string;
    /**
     * 角色 UID
     */
    roleUid?: string;
    /**
     * 角色区服
     */
    server?: string;
    /**
     * 已确认的数据来源路径
     */
    source?: string;
};
export namespace CommunityActivitySnapshotOut {
    /**
     * 活动查询状态
     */
    export enum status {
        SUCCESS = 'success',
        EMPTY = 'empty',
        LIMITED = 'limited',
        UNAVAILABLE = 'unavailable',
        FAILED = 'failed',
    }
}

