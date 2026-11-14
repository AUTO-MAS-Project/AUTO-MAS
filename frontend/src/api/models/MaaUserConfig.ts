/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaUserConfig_Data } from './MaaUserConfig_Data';
import type { MaaUserConfig_Info } from './MaaUserConfig_Info';
import type { MaaUserConfig_Notify } from './MaaUserConfig_Notify';
import type { MaaUserConfig_plugin_info } from './MaaUserConfig_plugin_info';
import type { MaaUserConfig_plugin_notify } from './MaaUserConfig_plugin_notify';
import type { MaaUserConfig_Stage } from './MaaUserConfig_Stage';
import type { MaaUserConfig_Task } from './MaaUserConfig_Task';
export type MaaUserConfig = {
    info?: (MaaUserConfig_plugin_info | null);
    /**
     * 用户通知
     */
    notify?: (MaaUserConfig_plugin_notify | null);
    Data?: (MaaUserConfig_Data | null);
    Info?: (MaaUserConfig_Info | null);
    Notify?: (MaaUserConfig_Notify | null);
    Stage?: (MaaUserConfig_Stage | null);
    Task?: (MaaUserConfig_Task | null);
};

