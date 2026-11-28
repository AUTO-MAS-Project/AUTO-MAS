/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdUserConfig_Data } from './ZzzOdUserConfig_Data';
import type { ZzzOdUserConfig_Game } from './ZzzOdUserConfig_Game';
import type { ZzzOdUserConfig_Info } from './ZzzOdUserConfig_Info';
import type { ZzzOdUserConfig_Notify } from './ZzzOdUserConfig_Notify';
import type { ZzzOdUserConfig_OneDragon } from './ZzzOdUserConfig_OneDragon';
import type { ZzzOdUserConfig_plugin_game } from './ZzzOdUserConfig_plugin_game';
export type ZzzOdUserConfig = {
    /**
     * 游戏与设备
     */
    game?: (ZzzOdUserConfig_plugin_game | null);
    Data?: (ZzzOdUserConfig_Data | null);
    Game?: (ZzzOdUserConfig_Game | null);
    Info?: (ZzzOdUserConfig_Info | null);
    Notify?: (ZzzOdUserConfig_Notify | null);
    OneDragon?: (ZzzOdUserConfig_OneDragon | null);
};

