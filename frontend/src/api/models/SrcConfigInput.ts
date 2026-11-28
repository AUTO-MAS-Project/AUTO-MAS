/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SrcConfig_gameInput } from './SrcConfig_gameInput';
import type { SrcConfig_InfoInput } from './SrcConfig_InfoInput';
import type { SrcConfig_plugin_infoInput } from './SrcConfig_plugin_infoInput';
import type { SrcConfig_RunInput } from './SrcConfig_RunInput';
import type { SrcConfig_UpdateInput } from './SrcConfig_UpdateInput';
export type SrcConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (SrcConfig_gameInput | null);
    info?: (SrcConfig_plugin_infoInput | null);
    Update?: (SrcConfig_UpdateInput | null);
    Info?: (SrcConfig_InfoInput | null);
    Run?: (SrcConfig_RunInput | null);
};

