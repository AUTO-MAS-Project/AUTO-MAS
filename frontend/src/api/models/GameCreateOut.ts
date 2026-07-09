/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameConfig } from './GameConfig';
export type GameCreateOut = {
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
     * 新创建的游戏 ID
     */
    gameId: string;
    /**
     * 游戏配置数据
     */
    data: GameConfig;
};

