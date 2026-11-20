/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralGame_action } from './GeneralGame_action';
import type { GeneralGame_creation } from './GeneralGame_creation';
import type { GeneralGame_devicesCollection } from './GeneralGame_devicesCollection';
import type { GeneralGame_info } from './GeneralGame_info';
export type GeneralGameDocument = {
    info?: (GeneralGame_info | null);
    /**
     * 游戏操作
     */
    action?: (GeneralGame_action | null);
    /**
     * 新建实例
     */
    creation?: (GeneralGame_creation | null);
    devices?: GeneralGame_devicesCollection;
};

