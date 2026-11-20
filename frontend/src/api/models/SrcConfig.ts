/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SrcConfig_game } from './SrcConfig_game';
import type { SrcConfig_Info } from './SrcConfig_Info';
import type { SrcConfig_Run } from './SrcConfig_Run';
import type { SrcConfig_Update } from './SrcConfig_Update';
export type SrcConfig = {
    /**
     * 游戏与设备
     */
    game?: (SrcConfig_game | null);
    Update?: (SrcConfig_Update | null);
    Info?: (SrcConfig_Info | null);
    Run?: (SrcConfig_Run | null);
};

