/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WhimboxUserConfig_Data } from './WhimboxUserConfig_Data';
import type { WhimboxUserConfig_Info } from './WhimboxUserConfig_Info';
import type { WhimboxUserConfig_Notify } from './WhimboxUserConfig_Notify';
import type { WhimboxUserConfig_OneDragon } from './WhimboxUserConfig_OneDragon';
import type { WhimboxUserConfig_plugin_info } from './WhimboxUserConfig_plugin_info';
import type { WhimboxUserConfig_plugin_notify } from './WhimboxUserConfig_plugin_notify';
import type { WhimboxUserConfig_Task } from './WhimboxUserConfig_Task';
export type WhimboxUserConfig = {
    info?: (WhimboxUserConfig_plugin_info | null);
    /**
     * 用户通知
     */
    notify?: (WhimboxUserConfig_plugin_notify | null);
    Data?: (WhimboxUserConfig_Data | null);
    Info?: (WhimboxUserConfig_Info | null);
    Notify?: (WhimboxUserConfig_Notify | null);
    OneDragon?: (WhimboxUserConfig_OneDragon | null);
    Task?: (WhimboxUserConfig_Task | null);
};

