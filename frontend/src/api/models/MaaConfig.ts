/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaConfig_game } from './MaaConfig_game';
import type { MaaConfig_Info } from './MaaConfig_Info';
import type { MaaConfig_plugin_info } from './MaaConfig_plugin_info';
import type { MaaConfig_Run } from './MaaConfig_Run';
import type { MaaConfig_Update } from './MaaConfig_Update';
export type MaaConfig = {
    /**
     * 游戏与设备
     */
    game?: (MaaConfig_game | null);
    info?: (MaaConfig_plugin_info | null);
    Info?: (MaaConfig_Info | null);
    Run?: (MaaConfig_Run | null);
    Update?: (MaaConfig_Update | null);
};

