/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIConfig_Game } from './BetterGIConfig_Game';
import type { BetterGIConfig_Run } from './BetterGIConfig_Run';
import type { GeneralConfig_Info } from './GeneralConfig_Info';
export type BetterGIConfig = {
    /**
     * 脚本基础信息
     */
    Info?: (GeneralConfig_Info | null);
    /**
     * 运行配置
     */
    Run?: (BetterGIConfig_Run | null);
    /**
     * 游戏配置
     */
    Game?: (BetterGIConfig_Game | null);
};

