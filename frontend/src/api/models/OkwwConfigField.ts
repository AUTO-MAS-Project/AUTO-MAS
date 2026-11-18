/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OkwwConfigField = {
    name: string;
    disabled?: boolean;
    minimum?: (number | null);
    maximum?: (number | null);
    integer?: boolean;
    type: OkwwConfigField.type;
    options?: Array<string>;
    parent?: (string | null);
    choices?: Array<string>;
};
export namespace OkwwConfigField {
    export enum type {
        BOOL = 'bool',
        NUMBER = 'number',
        STRING = 'string',
        SELECT = 'select',
        MULTI_SELECTION = 'multi_selection',
        JSON = 'json',
    }
}

