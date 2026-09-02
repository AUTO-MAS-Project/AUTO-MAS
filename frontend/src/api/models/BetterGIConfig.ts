/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIConfig_Game } from './BetterGIConfig_Game';
import type { BetterGIConfig_Info } from './BetterGIConfig_Info';
import type { BetterGIConfig_Run } from './BetterGIConfig_Run';
export type BetterGIConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (BetterGIConfig_Info | null);
    /**
     * 运行配置
     */
    Run?: (BetterGIConfig_Run | null);
    /**
     * 游戏配置
     */
    Game?: (BetterGIConfig_Game | null);
};
