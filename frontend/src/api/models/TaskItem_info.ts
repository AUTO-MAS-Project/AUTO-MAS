/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskMode } from './TaskMode';
import type { TaskTriggerReason } from './TaskTriggerReason';
export type TaskItem_info = {
    name?: (string | null);
    mode?: (TaskMode | null);
    status?: ('pending' | 'running' | 'success' | 'error' | 'cancelled' | null);
    trigger?: (TaskTriggerReason | null);
    readonly result?: (string | null);
};

