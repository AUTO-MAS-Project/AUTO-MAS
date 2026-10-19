/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HistoryIndexItem = {
    id: number;
    time: string;
    username: string;
    script_name: string;
    status: HistoryIndexItem.status;
    message: string;
    storage_error_count?: number;
};
export namespace HistoryIndexItem {
    export enum status {
        SUCCESS = 'success',
        ERROR = 'error',
        SKIPPED = 'skipped',
        CANCELLED = 'cancelled',
    }
}

