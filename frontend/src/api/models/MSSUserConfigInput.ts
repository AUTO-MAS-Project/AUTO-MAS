/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MSSUserConfig_DataInput } from './MSSUserConfig_DataInput';
import type { MSSUserConfig_DeviceInput } from './MSSUserConfig_DeviceInput';
import type { MSSUserConfig_gameInput } from './MSSUserConfig_gameInput';
import type { MSSUserConfig_InfoInput } from './MSSUserConfig_InfoInput';
import type { MSSUserConfig_NotifyInput } from './MSSUserConfig_NotifyInput';
import type { MSSUserConfig_TaskInput } from './MSSUserConfig_TaskInput';
export type MSSUserConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (MSSUserConfig_gameInput | null);
    Data?: (MSSUserConfig_DataInput | null);
    Device?: (MSSUserConfig_DeviceInput | null);
    Info?: (MSSUserConfig_InfoInput | null);
    Notify?: (MSSUserConfig_NotifyInput | null);
    Task?: (MSSUserConfig_TaskInput | null);
};

