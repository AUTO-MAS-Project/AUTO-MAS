/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BetterGIUserConfig_Data } from './BetterGIUserConfig_Data';
import type { BetterGIUserConfig_game } from './BetterGIUserConfig_game';
import type { BetterGIUserConfig_Info } from './BetterGIUserConfig_Info';
import type { BetterGIUserConfig_Notify } from './BetterGIUserConfig_Notify';
import type { BetterGIUserConfig_OneDragon } from './BetterGIUserConfig_OneDragon';
import type { BetterGIUserConfig_plugin_info } from './BetterGIUserConfig_plugin_info';
import type { BetterGIUserConfig_plugin_notify } from './BetterGIUserConfig_plugin_notify';
import type { BetterGIUserConfig_Switch } from './BetterGIUserConfig_Switch';
import type { BetterGIUserConfig_Task } from './BetterGIUserConfig_Task';
export type BetterGIUserConfig = {
    /**
     * 游戏与设备
     */
    game?: (BetterGIUserConfig_game | null);
    info?: (BetterGIUserConfig_plugin_info | null);
    /**
     * 用户通知
     */
    notify?: (BetterGIUserConfig_plugin_notify | null);
    Data?: (BetterGIUserConfig_Data | null);
    Info?: (BetterGIUserConfig_Info | null);
    Notify?: (BetterGIUserConfig_Notify | null);
    OneDragon?: (BetterGIUserConfig_OneDragon | null);
    Switch?: (BetterGIUserConfig_Switch | null);
    Task?: (BetterGIUserConfig_Task | null);
};

