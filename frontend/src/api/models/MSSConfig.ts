/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MSSConfig_Device } from './MSSConfig_Device';
import type { MSSConfig_Embedded } from './MSSConfig_Embedded';
import type { MSSConfig_Game } from './MSSConfig_Game';
import type { MSSConfig_Info } from './MSSConfig_Info';
import type { MSSConfig_plugin_game } from './MSSConfig_plugin_game';
import type { MSSConfig_plugin_info } from './MSSConfig_plugin_info';
import type { MSSConfig_Run } from './MSSConfig_Run';
import type { MSSConfig_Selection } from './MSSConfig_Selection';
import type { MSSConfig_Task } from './MSSConfig_Task';
import type { MSSConfig_Update } from './MSSConfig_Update';
export type MSSConfig = {
    /**
     * 游戏与设备
     */
    game?: (MSSConfig_plugin_game | null);
    info?: (MSSConfig_plugin_info | null);
    Device?: (MSSConfig_Device | null);
    Embedded?: (MSSConfig_Embedded | null);
    Game?: (MSSConfig_Game | null);
    Info?: (MSSConfig_Info | null);
    Run?: (MSSConfig_Run | null);
    Selection?: (MSSConfig_Selection | null);
    Task?: (MSSConfig_Task | null);
    Update?: (MSSConfig_Update | null);
};

