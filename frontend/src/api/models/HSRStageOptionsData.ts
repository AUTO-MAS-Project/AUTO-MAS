/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRDynamicStageCategory } from './HSRDynamicStageCategory';
export type HSRStageOptionsData = {
    /**
     * 体力副本执行脚本
     */
    engine: HSRStageOptionsData.engine;
    /**
     * 选项来源文件或目录
     */
    source?: (string | null);
    /**
     * 体力副本分类列表
     */
    categories?: Array<HSRDynamicStageCategory>;
};
export namespace HSRStageOptionsData {
    /**
     * 体力副本执行脚本
     */
    export enum engine {
        M7A = 'M7A',
        SRA = 'SRA',
    }
}
