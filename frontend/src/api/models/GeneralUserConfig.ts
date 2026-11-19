/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig_Data } from './GeneralUserConfig_Data';
import type { GeneralUserConfig_game } from './GeneralUserConfig_game';
import type { GeneralUserConfig_Info } from './GeneralUserConfig_Info';
import type { GeneralUserConfig_Notify } from './GeneralUserConfig_Notify';
export type GeneralUserConfig = {
    /**
     * 游戏与设备
     */
    game?: (GeneralUserConfig_game | null);
    Data?: (GeneralUserConfig_Data | null);
    Info?: (GeneralUserConfig_Info | null);
    Notify?: (GeneralUserConfig_Notify | null);
};

