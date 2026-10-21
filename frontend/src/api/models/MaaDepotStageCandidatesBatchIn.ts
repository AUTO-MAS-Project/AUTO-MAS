/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ScriptDeleteIn } from './ScriptDeleteIn';
export type MaaDepotStageCandidatesBatchIn = {
    script: ScriptDeleteIn;
    /**
     * 需要查询候选关卡的物品ID
     */
    itemIds: Array<string>;
};

