/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WhimboxConfig_game } from './WhimboxConfig_game';
import type { WhimboxConfig_Info } from './WhimboxConfig_Info';
import type { WhimboxConfig_plugin_info } from './WhimboxConfig_plugin_info';
import type { WhimboxConfig_Run } from './WhimboxConfig_Run';
import type { WhimboxConfig_Update } from './WhimboxConfig_Update';
export type WhimboxConfig = {
    /**
     * 游戏与设备
     */
    game?: (WhimboxConfig_game | null);
    info?: (WhimboxConfig_plugin_info | null);
    Info?: (WhimboxConfig_Info | null);
    Run?: (WhimboxConfig_Run | null);
    Update?: (WhimboxConfig_Update | null);
};

