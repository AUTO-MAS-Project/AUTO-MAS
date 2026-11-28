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
    data?: (GeneralGameInput | LDPlayerGameInput | ModAvdGameInput | MuMuGameInput | WinProcessGameInput);
};
export namespace GameCreateIn {
    export enum type {
        GENERAL_EMULATOR = 'general_emulator',
        LDPLAYER = 'ldplayer',
        AVD = 'avd',
        MUMU = 'mumu',
        WIN_PROCESS = 'win_process',
    }
}

