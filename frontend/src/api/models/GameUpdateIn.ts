/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralGameInput } from './GeneralGameInput';
import type { LDPlayerGameInput } from './LDPlayerGameInput';
import type { ModAvdGameInput } from './ModAvdGameInput';
import type { MuMuGameInput } from './MuMuGameInput';
import type { WinProcessGameInput } from './WinProcessGameInput';
export type GameUpdateIn = {
    gameId: string;
    data: (MuMuGameInput | LDPlayerGameInput | ModAvdGameInput | GeneralGameInput | WinProcessGameInput);
};

