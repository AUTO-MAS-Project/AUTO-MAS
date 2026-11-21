/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SrcUserConfig_Data } from './SrcUserConfig_Data';
import type { SrcUserConfig_game } from './SrcUserConfig_game';
import type { SrcUserConfig_Info } from './SrcUserConfig_Info';
import type { SrcUserConfig_Notify } from './SrcUserConfig_Notify';
import type { SrcUserConfig_plugin_info } from './SrcUserConfig_plugin_info';
import type { SrcUserConfig_plugin_notify } from './SrcUserConfig_plugin_notify';
import type { SrcUserConfig_Stage } from './SrcUserConfig_Stage';
export type SrcUserConfig = {
    /**
     * 游戏与设备
     */
    game?: (SrcUserConfig_game | null);
    info?: (SrcUserConfig_plugin_info | null);
    /**
     * 用户通知
     */
    notify?: (SrcUserConfig_plugin_notify | null);
    Data?: (SrcUserConfig_Data | null);
    Info?: (SrcUserConfig_Info | null);
    Notify?: (SrcUserConfig_Notify | null);
    Stage?: (SrcUserConfig_Stage | null);
};

