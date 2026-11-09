/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskItemDocument } from './TaskItemDocument';
import type { TaskMode } from './TaskMode';
import type { TaskTriggerReason } from './TaskTriggerReason';
import type { WSTaskScriptIdentityData } from './WSTaskScriptIdentityData';
/**
 * 一个运行中任务的 HTTP 初始快照。
 */
export type TaskRuntimeSnapshotItem = {
    task: TaskItemDocument;
    /**
     * 任务 ID
     */
    taskId: string;
    /**
     * 脚本执行模式; 循环运行的脚本同样按 AutoProxy 执行
     */
    mode: TaskMode;
    /**
     * 任务触发原因
     */
    trigger?: TaskTriggerReason;
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
     * 任务关联的托管静态标识
     */
    scripts?: Array<WSTaskScriptIdentityData>;
    /**
     * 任务当前日志
     */
    log?: string;
    /**
     * 日志基线序号，缺失时不能追加
     */
    logSeq?: (number | null);
    /**
     * 快照日志在来源中的起始行号
     */
    logFirstLine?: number;
};

