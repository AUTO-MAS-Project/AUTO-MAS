/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PanelBinding = {
    surface: PanelBinding.surface;
    page: string;
    scriptType?: (string | null);
    planType?: (string | null);
    channel?: (string | null);
};
export namespace PanelBinding {
    export enum surface {
        SCRIPT = 'script',
        SETUP = 'setup',
        USER = 'user',
        PLAN = 'plan',
        SETTINGS = 'settings',
        NOTIFICATION = 'notification',
        EXTRA = 'extra',
    }
}

