/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CloseReason } from './CloseReason';
import type { Node } from './Node';
import type { TaskLogAnalysisCursor } from './TaskLogAnalysisCursor';
export type TaskLogAnalysisPage = {
    nodes: Array<Node>;
    cursor: (TaskLogAnalysisCursor | null);
    hasMore: boolean;
    closeReason: (CloseReason | null);
};
