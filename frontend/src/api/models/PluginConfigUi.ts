/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UiHintsMap } from './UiHintsMap';
import type { UiSection } from './UiSection';
import type { UiStep } from './UiStep';
import type { UiTablesList } from './UiTablesList';
export type PluginConfigUi = {
    hints?: UiHintsMap;
    tables?: UiTablesList;
    steps?: Array<UiStep>;
    sections?: Record<string, UiSection>;
};

