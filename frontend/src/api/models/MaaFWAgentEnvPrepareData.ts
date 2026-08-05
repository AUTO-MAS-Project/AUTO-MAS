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
    /**
     * Prepared Runtime Pool runtime ID
     */
    runtimeId?: (string | null);
    /**
     * Prepared Runtime Pool identity
     */
    poolId?: (string | null);
    /**
     * Prepared runtime Python executable
     */
    pythonExecutable?: (string | null);
    /**
     * Prepared runtime virtual environment
     */
    venvPath?: (string | null);
};

