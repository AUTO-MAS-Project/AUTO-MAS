/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SrcUserConfig_DataInput } from './SrcUserConfig_DataInput';
import type { SrcUserConfig_gameInput } from './SrcUserConfig_gameInput';
import type { SrcUserConfig_InfoInput } from './SrcUserConfig_InfoInput';
import type { SrcUserConfig_NotifyInput } from './SrcUserConfig_NotifyInput';
import type { SrcUserConfig_StageInput } from './SrcUserConfig_StageInput';
export type SrcUserConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (SrcUserConfig_gameInput | null);
    Data?: (SrcUserConfig_DataInput | null);
    Info?: (SrcUserConfig_InfoInput | null);
    Notify?: (SrcUserConfig_NotifyInput | null);
    Stage?: (SrcUserConfig_StageInput | null);
};

