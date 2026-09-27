/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameSignAccountGroupConfig } from './GameSignAccountGroupConfig';
/**
 * 游戏社区账号组更新请求
 */
export type GameSignAccountUpdateIn = {
    /**
     * 编辑租约令牌
     */
    editLeaseToken?: (string | null);
    /**
     * 进入编辑时的基础指纹
     */
    baseVersion?: (string | null);
    /**
     * 账号组 UUID
     */
    accountId: string;
    /**
     * 账号组配置
     */
    data: GameSignAccountGroupConfig;
};

