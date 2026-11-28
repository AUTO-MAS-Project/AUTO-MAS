/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralUserConfig_DataInput } from './GeneralUserConfig_DataInput';
import type { GeneralUserConfig_gameInput } from './GeneralUserConfig_gameInput';
import type { GeneralUserConfig_InfoInput } from './GeneralUserConfig_InfoInput';
import type { GeneralUserConfig_NotifyInput } from './GeneralUserConfig_NotifyInput';
export type GeneralUserConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (GeneralUserConfig_gameInput | null);
    Data?: (GeneralUserConfig_DataInput | null);
    Info?: (GeneralUserConfig_InfoInput | null);
    Notify?: (GeneralUserConfig_NotifyInput | null);
};

