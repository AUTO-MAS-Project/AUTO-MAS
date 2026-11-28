/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHUserConfig_DataInput } from './BAAHUserConfig_DataInput';
import type { BAAHUserConfig_gameInput } from './BAAHUserConfig_gameInput';
import type { BAAHUserConfig_InfoInput } from './BAAHUserConfig_InfoInput';
import type { BAAHUserConfig_NotifyInput } from './BAAHUserConfig_NotifyInput';
export type BAAHUserConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (BAAHUserConfig_gameInput | null);
    Data?: (BAAHUserConfig_DataInput | null);
    Info?: (BAAHUserConfig_InfoInput | null);
    Notify?: (BAAHUserConfig_NotifyInput | null);
};

