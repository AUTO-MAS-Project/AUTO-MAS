/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ComboBoxItem } from './ComboBoxItem';
import type { MaaActivityItem } from './MaaActivityItem';
import type { MaaResourceItem } from './MaaResourceItem';
export type MaaStageOverview = {
    Activity: Array<MaaActivityItem>;
    ActivityTemplate: Array<'material' | 'orundum'>;
    ActivityStatus: MaaStageOverview.ActivityStatus;
    ActivityUpdatedAt: string;
    Resource: Array<MaaResourceItem>;
    Options: Array<ComboBoxItem>;
};
export namespace MaaStageOverview {
    export enum ActivityStatus {
        READY = 'ready',
        EMPTY = 'empty',
        STALE = 'stale',
        UNAVAILABLE = 'unavailable',
    }
}

