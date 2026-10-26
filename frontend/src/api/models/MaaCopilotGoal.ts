/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaCopilotGoal = {
    kind: MaaCopilotGoal.kind;
    target_id: string;
    to_level: number;
};
export namespace MaaCopilotGoal {
    export enum kind {
        ELITE = 'elite',
        SKILL = 'skill',
        MASTERY = 'mastery',
        MODULE = 'module',
    }
}

