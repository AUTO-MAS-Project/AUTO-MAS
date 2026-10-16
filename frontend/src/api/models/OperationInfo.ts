/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OperationState } from './OperationState';
export type OperationInfo = {
    operationId: string;
    configUid: string;
    field: string;
    owner?: (string | null);
    state?: OperationState;
    cancellable?: boolean;
    createdAt: string;
    completedAt?: (string | null);
    errorCode?: (string | null);
};

