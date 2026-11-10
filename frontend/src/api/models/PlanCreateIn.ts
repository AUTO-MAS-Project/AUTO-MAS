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
        MAA_PLAN = 'MaaPlan',
        MAA_END_PLAN = 'MaaEndPlan',
        BAAHPLAN = 'BAAHPlan',
        MSSPLAN = 'MSSPlan',
        UNIVERSAL_PLAN = 'UniversalPlan',
        OK_NTE_PLAN = 'OkNtePlan',
    }
}

