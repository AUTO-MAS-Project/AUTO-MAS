/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaEndUserConfig_Data } from './MaaEndUserConfig_Data';
import type { MaaEndUserConfig_game } from './MaaEndUserConfig_game';
import type { MaaEndUserConfig_Info } from './MaaEndUserConfig_Info';
import type { MaaEndUserConfig_Notify } from './MaaEndUserConfig_Notify';
import type { MaaEndUserConfig_Task } from './MaaEndUserConfig_Task';
export type MaaEndUserConfig = {
    /**
     * 游戏与设备
     */
    game?: (MaaEndUserConfig_game | null);
    Data?: (MaaEndUserConfig_Data | null);
    Info?: (MaaEndUserConfig_Info | null);
    Notify?: (MaaEndUserConfig_Notify | null);
    Task?: (MaaEndUserConfig_Task | null);
};

