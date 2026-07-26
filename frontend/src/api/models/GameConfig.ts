/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GameConfig_Cache } from './GameConfig_Cache';
import type { GameConfig_Data } from './GameConfig_Data';
import type { GameConfig_Info } from './GameConfig_Info';
export type GameConfig = {
    /**
     * 游戏基础信息
     */
    Info?: (GameConfig_Info | null);
    /**
     * 游戏定位数据
     */
    Data?: (GameConfig_Data | null);
    /**
     * 只读 provider 检查缓存
     */
    Cache?: (GameConfig_Cache | null);
    /**
     * 用于并发更新校验的配置版本
     */
    Revision?: (number | null);
};

