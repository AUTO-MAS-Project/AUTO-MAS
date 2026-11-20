/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WinProcessGame_action } from './WinProcessGame_action';
import type { WinProcessGame_devicesCollection } from './WinProcessGame_devicesCollection';
import type { WinProcessGame_info } from './WinProcessGame_info';
export type WinProcessGameDocument = {
    /**
     * 游戏信息
     */
    info?: (WinProcessGame_info | null);
    /**
     * 游戏操作
     */
    action?: (WinProcessGame_action | null);
    devices?: WinProcessGame_devicesCollection;
};

