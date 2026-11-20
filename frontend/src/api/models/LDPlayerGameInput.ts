/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LDPlayerGame_actionInput } from './LDPlayerGame_actionInput';
import type { LDPlayerGame_creationInput } from './LDPlayerGame_creationInput';
import type { LDPlayerGame_infoInput } from './LDPlayerGame_infoInput';
export type LDPlayerGameInput = {
    info?: (LDPlayerGame_infoInput | null);
    /**
     * 游戏操作
     */
    action?: (LDPlayerGame_actionInput | null);
    /**
     * 新建实例
     */
    creation?: (LDPlayerGame_creationInput | null);
};

