/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaUserConfig_DataInput } from './MaaUserConfig_DataInput';
import type { MaaUserConfig_InfoInput } from './MaaUserConfig_InfoInput';
import type { MaaUserConfig_NotifyInput } from './MaaUserConfig_NotifyInput';
import type { MaaUserConfig_plugin_infoInput } from './MaaUserConfig_plugin_infoInput';
import type { MaaUserConfig_plugin_notifyInput } from './MaaUserConfig_plugin_notifyInput';
import type { MaaUserConfig_StageInput } from './MaaUserConfig_StageInput';
import type { MaaUserConfig_TaskInput } from './MaaUserConfig_TaskInput';
export type MaaUserConfigInput = {
    info?: (MaaUserConfig_plugin_infoInput | null);
    /**
     * 用户通知
     */
    notify?: (MaaUserConfig_plugin_notifyInput | null);
    Data?: (MaaUserConfig_DataInput | null);
    Info?: (MaaUserConfig_InfoInput | null);
    Notify?: (MaaUserConfig_NotifyInput | null);
    Stage?: (MaaUserConfig_StageInput | null);
    Task?: (MaaUserConfig_TaskInput | null);
};

