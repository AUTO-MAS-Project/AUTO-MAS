/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type FrontendSurfaceMount = {
    mode: FrontendSurfaceMount.mode;
    pluginName: string;
    revision: string;
    activationId: string;
    entry?: (string | null);
};
export namespace FrontendSurfaceMount {
    export enum mode {
        DECLARATIVE = 'declarative',
        WHEEL = 'wheel',
    }
}

