/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FrontendSurfaceMount } from './FrontendSurfaceMount';
import type { JsonValue } from './JsonValue';
export type PluginBlockOut = {
    kind?: 'plugin';
    pageId: string;
    fallbackGroups: Array<string>;
    panelData?: (Record<string, JsonValue> | null);
    mount?: (FrontendSurfaceMount | null);
};

