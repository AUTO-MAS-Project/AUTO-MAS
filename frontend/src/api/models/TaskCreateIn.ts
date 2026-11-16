/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskMode } from './TaskMode';
import type { TaskSelectionNode } from './TaskSelectionNode';
export type TaskCreateIn = {
    mode: TaskMode;
    /**
     * 单入口任务要求树，顶层仅包含索引 0
     */
    tasks: Record<string, TaskSelectionNode>;
};

