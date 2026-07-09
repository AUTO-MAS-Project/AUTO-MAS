/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameConfig } from './GameConfig';
import type { GameConfigIndexItem } from './GameConfigIndexItem';
export type GameGetOut = {
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
     * 游戏索引列表
     */
    index: Array<GameConfigIndexItem>;
    /**
     * 游戏数据字典, key来自index
     */
    data: Record<string, GameConfig>;
};

