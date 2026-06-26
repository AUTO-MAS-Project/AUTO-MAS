/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWAgentEnvInfo = {
    /**
     * Agent child_exec declared by interface
     */
    childExec: string;
    /**
     * Actual executable used by agent
     */
    executable: string;
    /**
     * Agent runtime kind
     */
    runtimeKind?: (string | null);
    /**
     * Isolated venv path
     */
    isolatedVenvPath?: (string | null);
    /**
     * Agent runtime fallback reason
     */
    fallbackReason?: (string | null);
};

