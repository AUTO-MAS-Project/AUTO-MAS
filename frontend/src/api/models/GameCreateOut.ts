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
     * 新建游戏 UUID
     */
    gameId?: string;
    /**
     * 新建游戏配置
     */
    data?: GameConfig;
};

