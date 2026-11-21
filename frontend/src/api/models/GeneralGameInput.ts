/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralGame_actionInput } from './GeneralGame_actionInput';
import type { GeneralGame_creationInput } from './GeneralGame_creationInput';
import type { GeneralGame_infoInput } from './GeneralGame_infoInput';
export type GeneralGameInput = {
    info?: (GeneralGame_infoInput | null);
    /**
     * 游戏操作
     */
    action?: (GeneralGame_actionInput | null);
    /**
     * 新建实例
     */
    creation?: (GeneralGame_creationInput | null);
};

