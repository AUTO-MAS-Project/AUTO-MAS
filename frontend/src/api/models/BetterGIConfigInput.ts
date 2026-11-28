/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIConfig_GameInput } from './BetterGIConfig_GameInput';
import type { BetterGIConfig_InfoInput } from './BetterGIConfig_InfoInput';
import type { BetterGIConfig_plugin_gameInput } from './BetterGIConfig_plugin_gameInput';
import type { BetterGIConfig_plugin_infoInput } from './BetterGIConfig_plugin_infoInput';
import type { BetterGIConfig_RunInput } from './BetterGIConfig_RunInput';
import type { BetterGIConfig_UpdateInput } from './BetterGIConfig_UpdateInput';
export type BetterGIConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (BetterGIConfig_plugin_gameInput | null);
    info?: (BetterGIConfig_plugin_infoInput | null);
    Update?: (BetterGIConfig_UpdateInput | null);
    Game?: (BetterGIConfig_GameInput | null);
    Info?: (BetterGIConfig_InfoInput | null);
    Run?: (BetterGIConfig_RunInput | null);
};

