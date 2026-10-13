/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PluginListItem = {
    name: string;
    state: string;
    enabled: boolean;
    is_core?: boolean;
    is_local?: boolean;
    version?: (string | null);
    distribution?: (string | null);
    source?: (string | null);
    description?: string;
    requires?: Array<string>;
    wants?: Array<string>;
    last_error?: (string | null);
};

