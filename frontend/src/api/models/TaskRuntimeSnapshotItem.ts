/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSTaskScriptIdentityData } from './WSTaskScriptIdentityData';
import type { WSTaskScriptInfoData } from './WSTaskScriptInfoData';
/**
 * 一个运行中任务的 HTTP 初始快照。
 */
export type TaskRuntimeSnapshotItem = {
    /**
     * 任务 ID
     */
    taskId: string;
    /**
     * 任务模式
     */
    mode: TaskRuntimeSnapshotItem.mode;
    /**
     * 调度队列 ID
     */
    queueId?: (string | null);
    /**
     * 脚本 ID
     */
    scriptId?: (string | null);
    /**
     * 用户 ID
     */
    userId?: (string | null);
    /**
     * 任务是否正在停止
     */
    stopping?: boolean;
    /**
     * 任务关联的脚本静态标识
     */
    scripts?: Array<WSTaskScriptIdentityData>;
    /**
     * 任务脚本与用户状态
     */
    task_info?: Array<WSTaskScriptInfoData>;
    /**
     * 当前脚本日志
     */
    log?: string;
};
export namespace TaskRuntimeSnapshotItem {
    /**
     * 任务模式
     */
    export enum mode {
        AUTO_PROXY = 'AutoProxy',
        SCRIPT_CONFIG = 'ScriptConfig',
        UPDATE = 'Update',
    }
}

