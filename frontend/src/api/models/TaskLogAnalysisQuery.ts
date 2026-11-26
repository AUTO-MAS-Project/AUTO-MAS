/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskLogAnalysisCursor } from './TaskLogAnalysisCursor';
export type TaskLogAnalysisQuery = {
    scriptRunId: string;
    userRunId: string;
    cursor?: (TaskLogAnalysisCursor | null);
    limit?: number;
};
