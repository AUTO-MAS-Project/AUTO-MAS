/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WSTaskCyclePreviewData } from './WSTaskCyclePreviewData';
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
     * 脚本执行模式; 循环运行的脚本同样按 AutoProxy 执行
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
     * 循环运行的待运行条目, 仅循环任务非空
     */
    cycleNextList?: Array<WSTaskCyclePreviewData>;
    /**
     * 当前脚本日志
     */
    log?: string;
};
export namespace TaskRuntimeSnapshotItem {
    /**
     * 脚本执行模式; 循环运行的脚本同样按 AutoProxy 执行
     */
    export enum mode {
        AUTO_PROXY = 'AutoProxy',
        SCRIPT_CONFIG = 'ScriptConfig',
        UPDATE = 'Update',
    }
}

