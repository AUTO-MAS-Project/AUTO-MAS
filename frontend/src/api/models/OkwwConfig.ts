/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkwwConfig_Game } from './OkwwConfig_Game';
import type { OkwwConfig_Info } from './OkwwConfig_Info';
import type { OkwwConfig_plugin_game } from './OkwwConfig_plugin_game';
import type { OkwwConfig_Run } from './OkwwConfig_Run';
export type OkwwConfig = {
    /**
     * 游戏与设备
     */
    game?: (OkwwConfig_plugin_game | null);
    Game?: (OkwwConfig_Game | null);
    Info?: (OkwwConfig_Info | null);
    Run?: (OkwwConfig_Run | null);
};

