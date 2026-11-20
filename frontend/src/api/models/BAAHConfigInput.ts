/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHConfig_gameInput } from './BAAHConfig_gameInput';
import type { BAAHConfig_InfoInput } from './BAAHConfig_InfoInput';
import type { BAAHConfig_RunInput } from './BAAHConfig_RunInput';
import type { BAAHConfig_ScriptInput } from './BAAHConfig_ScriptInput';
import type { BAAHConfig_UpdateInput } from './BAAHConfig_UpdateInput';
export type BAAHConfigInput = {
    /**
     * 游戏与设备
     */
    game?: (BAAHConfig_gameInput | null);
    Update?: (BAAHConfig_UpdateInput | null);
    Info?: (BAAHConfig_InfoInput | null);
    Run?: (BAAHConfig_RunInput | null);
    Script?: (BAAHConfig_ScriptInput | null);
};

