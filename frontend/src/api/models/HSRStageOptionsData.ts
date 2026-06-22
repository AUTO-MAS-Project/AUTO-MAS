/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRDynamicStageCategory } from './HSRDynamicStageCategory';
export type HSRStageOptionsData = {
    /**
     * 娴ｆ挸濮忛崜顖涙拱閹笛嗩攽閼存碍婀?
     */
    engine: HSRStageOptionsData.engine;
    /**
     * 闁銆嶉弶銉︾爱閺傚洣娆㈤幋鏍窗瑜?
     */
    source?: (string | null);
    /**
     * 娴ｆ挸濮忛崜顖涙拱閸掑棛琚崚妤勩€?
     */
    categories?: Array<HSRDynamicStageCategory>;
};
export namespace HSRStageOptionsData {
    /**
     * 娴ｆ挸濮忛崜顖涙拱閹笛嗩攽閼存碍婀?
     */
    export enum engine {
        M7A = 'M7A',
        SRA = 'SRA',
    }
}
