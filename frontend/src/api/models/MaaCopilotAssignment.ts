/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaCopilotAssignment = {
    id: number;
    title: string;
    stage: string;
    author: string;
    state: MaaCopilotAssignment.state;
    missingOperators?: Array<string>;
    missingAlternatives?: Array<Array<string>>;
    gaps?: Array<string>;
    plannedReady?: boolean;
};
export namespace MaaCopilotAssignment {
    export enum state {
        READY = 'ready',
        TRAINING = 'training',
        MISSING = 'missing',
        UNKNOWN = 'unknown',
    }
}

