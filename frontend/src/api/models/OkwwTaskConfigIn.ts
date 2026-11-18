/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkwwTaskConfigIn = {
    scriptId: string;
    userId: string;
    kind: OkwwTaskConfigIn.kind;
    values: Record<string, any>;
};
export namespace OkwwTaskConfigIn {
    export enum kind {
        DAILY = 'daily',
        ECHO = 'echo',
        NIGHTMARE = 'nightmare',
        COMBAT = 'combat',
        CHARACTER = 'character',
        MONTHLY = 'monthly',
    }
}

