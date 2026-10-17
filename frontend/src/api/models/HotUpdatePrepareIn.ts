/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * 后端热更准备请求
 */
export type HotUpdatePrepareIn = {
    /**
     * 操作类型
     */
    action: HotUpdatePrepareIn.action;
    /**
     * 本次操作的唯一标识符
     */
    operationId: string;
    /**
     * 当前后端完整提交 SHA
     */
    baseCommit: string;
    /**
     * 目标后端完整提交 SHA
     */
    targetCommit: string;
};
export namespace HotUpdatePrepareIn {
    /**
     * 操作类型
     */
    export enum action {
        PREPARE = 'prepare',
        CANCEL = 'cancel',
        DRAIN = 'drain',
    }
}

