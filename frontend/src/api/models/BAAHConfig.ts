/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BAAHConfig_game } from './BAAHConfig_game';
import type { BAAHConfig_Info } from './BAAHConfig_Info';
import type { BAAHConfig_Run } from './BAAHConfig_Run';
import type { BAAHConfig_Script } from './BAAHConfig_Script';
import type { BAAHConfig_Update } from './BAAHConfig_Update';
export type BAAHConfig = {
    /**
     * 游戏与设备
     */
    game?: (BAAHConfig_game | null);
    Update?: (BAAHConfig_Update | null);
    Info?: (BAAHConfig_Info | null);
    Run?: (BAAHConfig_Run | null);
    Script?: (BAAHConfig_Script | null);
};

