/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralGameInput } from './GeneralGameInput';
import type { LDPlayerGameInput } from './LDPlayerGameInput';
import type { ModAvdGameInput } from './ModAvdGameInput';
import type { MuMuGameInput } from './MuMuGameInput';
import type { WinProcessGameInput } from './WinProcessGameInput';
export type GameCreateIn = {
    type: GameCreateIn.type;
    data?: (MuMuGameInput | LDPlayerGameInput | ModAvdGameInput | GeneralGameInput | WinProcessGameInput);
};
export namespace GameCreateIn {
    export enum type {
        MUMU = 'mumu',
        LDPLAYER = 'ldplayer',
        AVD = 'avd',
        GENERAL_EMULATOR = 'general_emulator',
        WIN_PROCESS = 'win_process',
    }
}

