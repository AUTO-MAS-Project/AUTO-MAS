/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWUserConfig_DataInput } from './MaaFWUserConfig_DataInput';
import type { MaaFWUserConfig_DeviceInput } from './MaaFWUserConfig_DeviceInput';
import type { MaaFWUserConfig_gameInput } from './MaaFWUserConfig_gameInput';
import type { MaaFWUserConfig_InfoInput } from './MaaFWUserConfig_InfoInput';
import type { MaaFWUserConfig_NotifyInput } from './MaaFWUserConfig_NotifyInput';
import type { MaaFWUserConfig_plugin_infoInput } from './MaaFWUserConfig_plugin_infoInput';
import type { MaaFWUserConfig_plugin_notifyInput } from './MaaFWUserConfig_plugin_notifyInput';
import type { MaaFWUserConfig_TaskInput } from './MaaFWUserConfig_TaskInput';
export type MaaFWUserConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (MaaFWUserConfig_gameInput | null);
    info?: (MaaFWUserConfig_plugin_infoInput | null);
    /**
     * 用户通知
     */
    notify?: (MaaFWUserConfig_plugin_notifyInput | null);
    Data?: (MaaFWUserConfig_DataInput | null);
    Device?: (MaaFWUserConfig_DeviceInput | null);
    Info?: (MaaFWUserConfig_InfoInput | null);
    Notify?: (MaaFWUserConfig_NotifyInput | null);
    Task?: (MaaFWUserConfig_TaskInput | null);
};

