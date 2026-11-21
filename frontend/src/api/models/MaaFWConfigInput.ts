/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWConfig_DeviceInput } from './MaaFWConfig_DeviceInput';
import type { MaaFWConfig_EmbeddedInput } from './MaaFWConfig_EmbeddedInput';
import type { MaaFWConfig_GameInput } from './MaaFWConfig_GameInput';
import type { MaaFWConfig_InfoInput } from './MaaFWConfig_InfoInput';
import type { MaaFWConfig_plugin_gameInput } from './MaaFWConfig_plugin_gameInput';
import type { MaaFWConfig_RunInput } from './MaaFWConfig_RunInput';
import type { MaaFWConfig_SelectionInput } from './MaaFWConfig_SelectionInput';
import type { MaaFWConfig_TaskInput } from './MaaFWConfig_TaskInput';
import type { MaaFWConfig_UpdateInput } from './MaaFWConfig_UpdateInput';
export type MaaFWConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (MaaFWConfig_plugin_gameInput | null);
    Device?: (MaaFWConfig_DeviceInput | null);
    Embedded?: (MaaFWConfig_EmbeddedInput | null);
    Game?: (MaaFWConfig_GameInput | null);
    Info?: (MaaFWConfig_InfoInput | null);
    Run?: (MaaFWConfig_RunInput | null);
    Selection?: (MaaFWConfig_SelectionInput | null);
    Task?: (MaaFWConfig_TaskInput | null);
    Update?: (MaaFWConfig_UpdateInput | null);
};

