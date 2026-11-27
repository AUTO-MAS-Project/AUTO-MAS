/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PanelArtifactInfo } from './PanelArtifactInfo';
import type { PanelBinding } from './PanelBinding';
export type PluginFrontendInfo = {
    manifestVersion?: number;
    revision: string;
    activationId: string;
    pages: Record<string, Record<string, PanelArtifactInfo>>;
    bindings: Array<PanelBinding>;
    diagnostics: Array<string>;
};

