/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSTaskCyclePreviewData } from './WSTaskCyclePreviewData';
import type { WSTaskPrefetchData } from './WSTaskPrefetchData';
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
     * 托管执行模式; 循环运行的托管同样按 AutoProxy 执行
     */
    mode: TaskRuntimeSnapshotItem.mode;
    /**
     * 是否为循环运行任务
     */
    isCycle?: boolean;
    /**
     * 调度队列 ID
     */
    queueId?: (string | null);
    /**
     * 托管 ID
     */
    scriptId?: (string | null);
    /**
     * 账号 ID
     */
    userId?: (string | null);
    /**
     * 任务是否正在停止
     */
    stopping?: boolean;
    /**
     * 任务关联的托管静态标识
     */
    scripts?: Array<WSTaskScriptIdentityData>;
    /**
     * 任务托管与账号状态
     */
    task_info?: Array<WSTaskScriptInfoData>;
    /**
     * 临时预下载状态
     */
    prefetch?: (WSTaskPrefetchData | null);
    /**
     * 循环运行的待运行条目, 仅循环任务非空
     */
    cycleNextList?: Array<WSTaskCyclePreviewData>;
    /**
     * 已推送的托管日志, 与下一条增量推送衔接
     */
    log?: string;
    /**
     * 已推送日志对应的推送序号
     */
    logSeq?: number;
    /**
     * 快照日志首行在完整日志里的行号
     */
    logFirstLine?: number;
};
export namespace TaskRuntimeSnapshotItem {
    /**
     * 托管执行模式; 循环运行的托管同样按 AutoProxy 执行
     */
    export enum mode {
        AUTO_PROXY = 'AutoProxy',
        SCRIPT_CONFIG = 'ScriptConfig',
        UPDATE = 'Update',
    }
}

