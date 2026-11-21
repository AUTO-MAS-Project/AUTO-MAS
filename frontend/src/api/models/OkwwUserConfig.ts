/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkwwUserConfig_Data } from './OkwwUserConfig_Data';
import type { OkwwUserConfig_game } from './OkwwUserConfig_game';
import type { OkwwUserConfig_Info } from './OkwwUserConfig_Info';
import type { OkwwUserConfig_Notify } from './OkwwUserConfig_Notify';
import type { OkwwUserConfig_Task } from './OkwwUserConfig_Task';
export type OkwwUserConfig = {
    /**
     * 游戏与设备
     */
    game?: (OkwwUserConfig_game | null);
    Data?: (OkwwUserConfig_Data | null);
    Info?: (OkwwUserConfig_Info | null);
    Notify?: (OkwwUserConfig_Notify | null);
    Task?: (OkwwUserConfig_Task | null);
};

