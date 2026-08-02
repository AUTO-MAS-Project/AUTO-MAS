/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaFWAgentEnvInfo } from './MaaFWAgentEnvInfo';
export type MaaFWAgentEnvPrepareData = {
    /**
     * MaaFW project root path
     */
    path: string;
    /**
     * Agent count
     */
    agentCount?: number;
    /**
     * Agent env info
     */
    agents?: Array<MaaFWAgentEnvInfo>;
    /**
     * Preparation logs
     */
    logs?: Array<string>;
};

