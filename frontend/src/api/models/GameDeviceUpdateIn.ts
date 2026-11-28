/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralDeviceInput } from './GeneralDeviceInput';
import type { LDPlayerDeviceInput } from './LDPlayerDeviceInput';
import type { ModAvdDeviceInput } from './ModAvdDeviceInput';
import type { MuMuDeviceInput } from './MuMuDeviceInput';
import type { WinProcessDeviceInput } from './WinProcessDeviceInput';
export type GameDeviceUpdateIn = {
    gameId: string;
    deviceId: string;
    data: (GeneralDeviceInput | LDPlayerDeviceInput | ModAvdDeviceInput | MuMuDeviceInput | WinProcessDeviceInput);
};

