/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 下载中心的可重复读取快照，不消费背景结果。
 */
export type DownloadSnapshot = {
    url: string;
    identity_type: DownloadSnapshot.identity_type;
    identity: (string | null);
    generation?: (string | null);
    state: DownloadSnapshot.state;
    path?: (string | null);
    error_code?: (string | null);
    writer_unconfirmed?: boolean;
    downloaded?: number;
    total?: number;
    speed?: number;
};
export namespace DownloadSnapshot {
    export enum identity_type {
        RID = 'rid',
        HASH = 'hash',
        NULL = 'null',
    }
    export enum state {
        NOT_FOUND = 'not_found',
        PENDING = 'pending',
        RUNNING = 'running',
        RETRYING = 'retrying',
        SUCCEEDED = 'succeeded',
        FAILED = 'failed',
        CANCELLING = 'cancelling',
        CANCELLED = 'cancelled',
    }
}

