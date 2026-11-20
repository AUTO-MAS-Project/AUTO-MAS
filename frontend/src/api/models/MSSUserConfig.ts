/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MSSUserConfig_Data } from './MSSUserConfig_Data';
import type { MSSUserConfig_Device } from './MSSUserConfig_Device';
import type { MSSUserConfig_game } from './MSSUserConfig_game';
import type { MSSUserConfig_Info } from './MSSUserConfig_Info';
import type { MSSUserConfig_Notify } from './MSSUserConfig_Notify';
import type { MSSUserConfig_Task } from './MSSUserConfig_Task';
export type MSSUserConfig = {
    /**
     * 游戏与设备
     */
    game?: (MSSUserConfig_game | null);
    Data?: (MSSUserConfig_Data | null);
    Device?: (MSSUserConfig_Device | null);
    Info?: (MSSUserConfig_Info | null);
    Notify?: (MSSUserConfig_Notify | null);
    Task?: (MSSUserConfig_Task | null);
};

