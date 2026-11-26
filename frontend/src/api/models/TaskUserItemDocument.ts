/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskUserItem_info } from './TaskUserItem_info';
import type { TaskUserItem_log_analysis } from './TaskUserItem_log_analysis';
import type { TaskUserItem_logsCollection } from './TaskUserItem_logsCollection';
export type TaskUserItemDocument = {
    log_analysis?: (TaskUserItem_log_analysis | null);
    info?: (TaskUserItem_info | null);
    logs?: TaskUserItem_logsCollection;
};

