/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameSignAccountDataOut } from './GameSignAccountDataOut';
import type { GameSignAccountInstanceOut } from './GameSignAccountInstanceOut';
/**
 * 游戏社区账号组列表响应
 */
export type GameSignAccountsListOut = {
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
     * 账号组列表
     */
    data?: Record<string, (Array<GameSignAccountInstanceOut> | GameSignAccountDataOut)>;
};

