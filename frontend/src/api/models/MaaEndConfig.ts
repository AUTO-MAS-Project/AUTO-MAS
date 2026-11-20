/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndConfig_Game } from './MaaEndConfig_Game';
import type { MaaEndConfig_Info } from './MaaEndConfig_Info';
import type { MaaEndConfig_plugin_game } from './MaaEndConfig_plugin_game';
import type { MaaEndConfig_Run } from './MaaEndConfig_Run';
import type { MaaEndConfig_Update } from './MaaEndConfig_Update';
export type MaaEndConfig = {
    /**
     * 游戏与设备
     */
    game?: (MaaEndConfig_plugin_game | null);
    Game?: (MaaEndConfig_Game | null);
    Info?: (MaaEndConfig_Info | null);
    Run?: (MaaEndConfig_Run | null);
    Update?: (MaaEndConfig_Update | null);
};

