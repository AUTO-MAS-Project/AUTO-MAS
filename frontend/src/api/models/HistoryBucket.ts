/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HistoryAggregateError } from './HistoryAggregateError';
import type { HistoryCounterStatistic } from './HistoryCounterStatistic';
import type { HistoryIndexItem } from './HistoryIndexItem';
import type { HistoryKeyedSnapshotStatistic } from './HistoryKeyedSnapshotStatistic';
import type { HistorySnapshotStatistic } from './HistorySnapshotStatistic';
export type HistoryBucket = {
    index?: Array<HistoryIndexItem>;
    data?: Record<string, (HistoryCounterStatistic | HistorySnapshotStatistic | HistoryKeyedSnapshotStatistic)>;
    aggregate_errors?: Array<HistoryAggregateError>;
};

