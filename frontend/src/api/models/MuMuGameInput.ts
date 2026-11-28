/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MuMuGame_actionInput } from './MuMuGame_actionInput';
import type { MuMuGame_creationInput } from './MuMuGame_creationInput';
import type { MuMuGame_infoInput } from './MuMuGame_infoInput';
export type MuMuGameInput = {
    info?: (MuMuGame_infoInput | null);
    /**
     * 游戏操作
     */
    action?: (MuMuGame_actionInput | null);
    /**
     * 新建实例
     */
    creation?: (MuMuGame_creationInput | null);
};

