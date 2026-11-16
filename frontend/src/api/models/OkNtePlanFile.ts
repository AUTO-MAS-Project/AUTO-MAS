/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkNtePlanField } from './OkNtePlanField';
export type OkNtePlanFile = {
    filename: string;
    displayName: string;
    taskIndex: (number | null);
    fields: Array<OkNtePlanField>;
    currentData: Record<string, any>;
    parseError?: boolean;
    overrides: Record<string, any>;
};

