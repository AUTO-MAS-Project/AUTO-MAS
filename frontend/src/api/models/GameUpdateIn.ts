/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameConfig } from './GameConfig';
export type GameUpdateIn = {
    /**
     * 游戏 UUID
     */
    gameId: string;
    /**
     * 游戏配置局部更新
     */
    data: GameConfig;
    /**
     * 期望的当前配置版本
     */
    expectedRevision?: (number | null);
};

