/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HistoryAttachment } from './HistoryAttachment';
import type { HistoryCounterStatistic } from './HistoryCounterStatistic';
import type { HistoryKeyedSnapshotStatistic } from './HistoryKeyedSnapshotStatistic';
import type { HistorySnapshotStatistic } from './HistorySnapshotStatistic';
import type { HistoryStorageIssue } from './HistoryStorageIssue';
export type HistoryDetail = {
    id: string;
    time: string;
    username: string;
    script_name: string;
    status: HistoryDetail.status;
    message: string;
    storage_error_count?: number;
    data?: Record<string, (HistoryCounterStatistic | HistorySnapshotStatistic | HistoryKeyedSnapshotStatistic)>;
    attachments?: Array<HistoryAttachment>;
    storage_errors?: Array<HistoryStorageIssue>;
    log_path?: (string | null);
    has_log_fallback?: boolean;
    log_content?: (string | null);
    log_available?: boolean;
    log_unavailable_reason?: (string | null);
};
export namespace HistoryDetail {
    export enum status {
        SUCCESS = 'success',
        ERROR = 'error',
        SKIPPED = 'skipped',
        CANCELLED = 'cancelled',
    }
}

