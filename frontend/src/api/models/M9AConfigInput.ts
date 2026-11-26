/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { M9AConfig_DeviceInput } from './M9AConfig_DeviceInput';
import type { M9AConfig_EmbeddedInput } from './M9AConfig_EmbeddedInput';
import type { M9AConfig_GameInput } from './M9AConfig_GameInput';
import type { M9AConfig_InfoInput } from './M9AConfig_InfoInput';
import type { M9AConfig_plugin_gameInput } from './M9AConfig_plugin_gameInput';
import type { M9AConfig_plugin_infoInput } from './M9AConfig_plugin_infoInput';
import type { M9AConfig_RunInput } from './M9AConfig_RunInput';
import type { M9AConfig_SelectionInput } from './M9AConfig_SelectionInput';
import type { M9AConfig_TaskInput } from './M9AConfig_TaskInput';
import type { M9AConfig_UpdateInput } from './M9AConfig_UpdateInput';
export type M9AConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (M9AConfig_plugin_gameInput | null);
    info?: (M9AConfig_plugin_infoInput | null);
    Device?: (M9AConfig_DeviceInput | null);
    Embedded?: (M9AConfig_EmbeddedInput | null);
    Game?: (M9AConfig_GameInput | null);
    Info?: (M9AConfig_InfoInput | null);
    Run?: (M9AConfig_RunInput | null);
    Selection?: (M9AConfig_SelectionInput | null);
    Task?: (M9AConfig_TaskInput | null);
    Update?: (M9AConfig_UpdateInput | null);
};

