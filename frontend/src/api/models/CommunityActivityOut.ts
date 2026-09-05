/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CommunityActivitySnapshotOut } from './CommunityActivitySnapshotOut';
/**
 * 游戏社区日常活动查询响应。
 */
export type CommunityActivityOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    /**
     * 按账号和游戏拆分的活动快照
     */
    data?: Array<CommunityActivitySnapshotOut>;
};

