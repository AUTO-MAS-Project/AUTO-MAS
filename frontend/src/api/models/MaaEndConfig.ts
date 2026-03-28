/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndConfig_Game } from './MaaEndConfig_Game';
import type { MaaEndConfig_Info } from './MaaEndConfig_Info';
import type { MaaEndConfig_Run } from './MaaEndConfig_Run';
export type MaaEndConfig = {
    /**
     * 脚本信息
     */
    Info?: (MaaEndConfig_Info | null);
    /**
     * 运行配置
     */
    Run?: (MaaEndConfig_Run | null);
    /**
     * 游戏配置
     */
    Game?: (MaaEndConfig_Game | null);
};

