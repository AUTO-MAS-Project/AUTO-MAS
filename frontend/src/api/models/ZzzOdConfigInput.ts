/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdConfig_GameInput } from './ZzzOdConfig_GameInput';
import type { ZzzOdConfig_InfoInput } from './ZzzOdConfig_InfoInput';
import type { ZzzOdConfig_plugin_gameInput } from './ZzzOdConfig_plugin_gameInput';
import type { ZzzOdConfig_RunInput } from './ZzzOdConfig_RunInput';
export type ZzzOdConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (ZzzOdConfig_plugin_gameInput | null);
    Game?: (ZzzOdConfig_GameInput | null);
    Info?: (ZzzOdConfig_InfoInput | null);
    Run?: (ZzzOdConfig_RunInput | null);
};

