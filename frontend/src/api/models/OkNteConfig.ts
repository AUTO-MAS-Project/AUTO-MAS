/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkNteConfig_Game } from './OkNteConfig_Game';
import type { OkNteConfig_Info } from './OkNteConfig_Info';
import type { OkNteConfig_plugin_game } from './OkNteConfig_plugin_game';
import type { OkNteConfig_Run } from './OkNteConfig_Run';
import type { OkNteConfig_Script } from './OkNteConfig_Script';
export type OkNteConfig = {
    /**
     * 游戏与设备
     */
    game?: (OkNteConfig_plugin_game | null);
    Game?: (OkNteConfig_Game | null);
    Info?: (OkNteConfig_Info | null);
    Run?: (OkNteConfig_Run | null);
    Script?: (OkNteConfig_Script | null);
};

