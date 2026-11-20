/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdConfig_Game } from './ZzzOdConfig_Game';
import type { ZzzOdConfig_Info } from './ZzzOdConfig_Info';
import type { ZzzOdConfig_plugin_game } from './ZzzOdConfig_plugin_game';
import type { ZzzOdConfig_Run } from './ZzzOdConfig_Run';
export type ZzzOdConfig = {
    /**
     * 游戏与设备
     */
    game?: (ZzzOdConfig_plugin_game | null);
    Game?: (ZzzOdConfig_Game | null);
    Info?: (ZzzOdConfig_Info | null);
    Run?: (ZzzOdConfig_Run | null);
};

