/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameSignAccountGroupConfigInput } from './GameSignAccountGroupConfigInput';
/**
 * 游戏社区账号组更新请求
 */
export type GameSignAccountUpdateIn = {
    /**
     * 账号组 UUID
     */
    accountId: string;
    /**
     * 账号组配置
     */
    data: GameSignAccountGroupConfigInput;
};

