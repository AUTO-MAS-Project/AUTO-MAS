/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginFrontendPlanCreationInfo } from './PluginFrontendPlanCreationInfo';
import type { PluginFrontendRouteAliasInfo } from './PluginFrontendRouteAliasInfo';
import type { PluginFrontendSurfaceInfo } from './PluginFrontendSurfaceInfo';
export type PluginFrontendTargetInfo = {
    scriptKey: string;
    scriptConfigType: string;
    userConfigType: (string | null);
    planConfigType: (string | null);
    displayName: (string | null);
    iconAsset: (string | null);
    surfaces: Record<string, PluginFrontendSurfaceInfo>;
    aliases: Array<PluginFrontendRouteAliasInfo>;
    planCreation: (PluginFrontendPlanCreationInfo | null);
};

