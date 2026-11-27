/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { M9AUserConfig_DataInput } from './M9AUserConfig_DataInput';
import type { M9AUserConfig_DeviceInput } from './M9AUserConfig_DeviceInput';
import type { M9AUserConfig_gameInput } from './M9AUserConfig_gameInput';
import type { M9AUserConfig_InfoInput } from './M9AUserConfig_InfoInput';
import type { M9AUserConfig_NotifyInput } from './M9AUserConfig_NotifyInput';
import type { M9AUserConfig_plugin_infoInput } from './M9AUserConfig_plugin_infoInput';
import type { M9AUserConfig_plugin_notifyInput } from './M9AUserConfig_plugin_notifyInput';
import type { M9AUserConfig_TaskInput } from './M9AUserConfig_TaskInput';
export type M9AUserConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (M9AUserConfig_gameInput | null);
    info?: (M9AUserConfig_plugin_infoInput | null);
    /**
     * 用户通知
     */
    notify?: (M9AUserConfig_plugin_notifyInput | null);
    Data?: (M9AUserConfig_DataInput | null);
    Device?: (M9AUserConfig_DeviceInput | null);
    Info?: (M9AUserConfig_InfoInput | null);
    Notify?: (M9AUserConfig_NotifyInput | null);
    Task?: (M9AUserConfig_TaskInput | null);
};

