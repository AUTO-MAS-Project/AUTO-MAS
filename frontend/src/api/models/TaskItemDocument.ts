/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskItem_current } from './TaskItem_current';
import type { TaskItem_execution } from './TaskItem_execution';
import type { TaskItem_info } from './TaskItem_info';
import type { TaskItem_scriptsCollection } from './TaskItem_scriptsCollection';
export type TaskItemDocument = {
    info?: (TaskItem_info | null);
    execution?: (TaskItem_execution | null);
    current?: (TaskItem_current | null);
    scripts?: TaskItem_scriptsCollection;
};

