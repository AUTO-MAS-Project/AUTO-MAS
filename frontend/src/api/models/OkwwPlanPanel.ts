/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OkwwConfigField } from './OkwwConfigField';
export type OkwwPlanPanel = {
    kind: OkwwPlanPanel.kind;
    filename: string;
    values: Record<string, any>;
    fields: Array<OkwwConfigField>;
    overrides: Record<string, any>;
    labels: Record<string, string>;
};
export namespace OkwwPlanPanel {
    export enum kind {
        DAILY = 'daily',
        ECHO = 'echo',
        NIGHTMARE = 'nightmare',
        COMBAT = 'combat',
        CHARACTER = 'character',
        MONTHLY = 'monthly',
    }
}

