/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LDPlayerGame_action } from './LDPlayerGame_action';
import type { LDPlayerGame_creation } from './LDPlayerGame_creation';
import type { LDPlayerGame_devicesCollection } from './LDPlayerGame_devicesCollection';
import type { LDPlayerGame_info } from './LDPlayerGame_info';
export type LDPlayerGameDocument = {
    info?: (LDPlayerGame_info | null);
    /**
     * 游戏操作
     */
    action?: (LDPlayerGame_action | null);
    /**
     * 新建实例
     */
    creation?: (LDPlayerGame_creation | null);
    devices?: LDPlayerGame_devicesCollection;
};

