/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaaCopilotGoal } from './MaaCopilotGoal';
export type MaaCopilotOperator = {
    operatorId: string;
    name: string;
    owned: boolean;
    optional?: boolean;
    demand?: number;
    currentElite?: number;
    currentLevel?: number;
    targetElite?: number;
    targetLevel?: number;
    manualLevel?: boolean;
    goals?: Array<MaaCopilotGoal>;
};

