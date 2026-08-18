/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PlanIndexItem = {
    /**
     * 唯一标识符
     */
    uid: string;
    /**
     * 配置类型
     */
    type: PlanIndexItem.type;
};
export namespace PlanIndexItem {
    /**
     * 配置类型
     */
    export enum type {
        MAA_PLAN_CONFIG = 'MaaPlanConfig',
        MAA_END_PLAN_CONFIG = 'MaaEndPlanConfig',
    }
}

