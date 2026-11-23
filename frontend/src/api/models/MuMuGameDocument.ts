/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MuMuGame_action } from './MuMuGame_action';
import type { MuMuGame_creation } from './MuMuGame_creation';
import type { MuMuGame_devicesCollection } from './MuMuGame_devicesCollection';
import type { MuMuGame_info } from './MuMuGame_info';
export type MuMuGameDocument = {
    info?: (MuMuGame_info | null);
    /**
     * 游戏操作
     */
    action?: (MuMuGame_action | null);
    /**
     * 新建实例
     */
    creation?: (MuMuGame_creation | null);
    devices?: MuMuGame_devicesCollection;
};

