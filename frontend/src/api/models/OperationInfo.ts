/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 宿主命令快照，业务参数和插件实例不进入外部契约。
 */
export type OperationInfo = {
    operationId: string;
    configUid: string;
    field: string;
    owner?: (string | null);
    state?: OperationInfo.state;
    cancellable?: boolean;
    createdAt: string;
    completedAt?: (string | null);
    errorCode?: (string | null);
};
export namespace OperationInfo {
    export enum state {
        QUEUED = 'queued',
        RUNNING = 'running',
        CANCELLING = 'cancelling',
        SUCCEEDED = 'succeeded',
        FAILED = 'failed',
        CANCELLED = 'cancelled',
    }
}

