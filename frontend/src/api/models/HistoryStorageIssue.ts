/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HistoryStorageIssue = {
    stage: HistoryStorageIssue.stage;
    attachment_index?: (number | null);
    source_path?: (string | null);
    target_path?: (string | null);
    error_type: string;
    message: string;
    recovered?: boolean;
};
export namespace HistoryStorageIssue {
    export enum stage {
        MKDIR = 'mkdir',
        WRITE_LOG = 'write_log',
        MOVE = 'move',
        COPY = 'copy',
        QUOTA = 'quota',
        CLEANUP = 'cleanup',
        DATABASE = 'database',
    }
}

