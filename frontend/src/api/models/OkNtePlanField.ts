/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkNtePlanRoutineItem } from './OkNtePlanRoutineItem';
export type OkNtePlanField = {
    name: string;
    label?: (string | null);
    type: string;
    value?: any;
    min?: (number | null);
    max?: (number | null);
    step?: (number | null);
    options?: (Array<string> | null);
    children?: (Array<OkNtePlanField> | null);
    itemDefinitions?: (Array<OkNtePlanRoutineItem> | null);
};

