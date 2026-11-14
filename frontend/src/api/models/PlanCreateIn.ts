/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PlanCreateIn = {
    type: PlanCreateIn.type;
    scriptId?: (string | null);
};
export namespace PlanCreateIn {
    export enum type {
        OKWW_PLAN = 'OkwwPlan',
        OK_NTE_PLAN = 'OkNtePlan',
        UNIVERSAL_PLAN = 'UniversalPlan',
        MAA_END_PLAN = 'MaaEndPlan',
        BAAHPLAN = 'BAAHPlan',
        MSSPLAN = 'MSSPlan',
        MAA_PLAN_CONFIG = 'MaaPlanConfig',
    }
}

