/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ZzzOdUserConfig_DataInput } from './ZzzOdUserConfig_DataInput';
import type { ZzzOdUserConfig_GameInput } from './ZzzOdUserConfig_GameInput';
import type { ZzzOdUserConfig_InfoInput } from './ZzzOdUserConfig_InfoInput';
import type { ZzzOdUserConfig_NotifyInput } from './ZzzOdUserConfig_NotifyInput';
import type { ZzzOdUserConfig_OneDragonInput } from './ZzzOdUserConfig_OneDragonInput';
import type { ZzzOdUserConfig_plugin_gameInput } from './ZzzOdUserConfig_plugin_gameInput';
export type ZzzOdUserConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (ZzzOdUserConfig_plugin_gameInput | null);
    Data?: (ZzzOdUserConfig_DataInput | null);
    Game?: (ZzzOdUserConfig_GameInput | null);
    Info?: (ZzzOdUserConfig_InfoInput | null);
    Notify?: (ZzzOdUserConfig_NotifyInput | null);
    OneDragon?: (ZzzOdUserConfig_OneDragonInput | null);
};

