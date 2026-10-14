/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskRuntimeSnapshotItem } from './TaskRuntimeSnapshotItem';
import type { WSTaskScriptIdentityData } from './WSTaskScriptIdentityData';
/**
 * 任务运行与定时队列 HTTP 初始快照。
 */
export type TaskRuntimeSnapshot = {
    tasks?: Array<TaskRuntimeSnapshotItem>;
    /**
     * 已启用定时队列关联的脚本静态标识
     */
    scheduledScripts?: Array<WSTaskScriptIdentityData>;
};

