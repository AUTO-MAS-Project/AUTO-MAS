/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWConfig_Device } from './MaaFWConfig_Device';
import type { MaaFWConfig_Embedded } from './MaaFWConfig_Embedded';
import type { MaaFWConfig_Game } from './MaaFWConfig_Game';
import type { MaaFWConfig_Info } from './MaaFWConfig_Info';
import type { MaaFWConfig_plugin_game } from './MaaFWConfig_plugin_game';
import type { MaaFWConfig_plugin_info } from './MaaFWConfig_plugin_info';
import type { MaaFWConfig_Run } from './MaaFWConfig_Run';
import type { MaaFWConfig_Selection } from './MaaFWConfig_Selection';
import type { MaaFWConfig_Task } from './MaaFWConfig_Task';
import type { MaaFWConfig_Update } from './MaaFWConfig_Update';
export type MaaFWConfig = {
    /**
     * 游戏与设备
     */
    game?: (MaaFWConfig_plugin_game | null);
    info?: (MaaFWConfig_plugin_info | null);
    Device?: (MaaFWConfig_Device | null);
    Embedded?: (MaaFWConfig_Embedded | null);
    Game?: (MaaFWConfig_Game | null);
    Info?: (MaaFWConfig_Info | null);
    Run?: (MaaFWConfig_Run | null);
    Selection?: (MaaFWConfig_Selection | null);
    Task?: (MaaFWConfig_Task | null);
    Update?: (MaaFWConfig_Update | null);
};

