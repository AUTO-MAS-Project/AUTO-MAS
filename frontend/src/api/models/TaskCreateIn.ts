/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskMode } from './TaskMode';
/**
 * 任务模式与可选队列、脚本、用户入口。
 */
export type TaskCreateIn = {
    /**
     * 任务模式
     */
    mode: TaskMode;
    /**
     * 队列 uid
     */
    queueId?: (string | null);
    /**
     * 脚本 uid
     */
    scriptId?: (string | null);
    /**
     * 用户 uid；队列任务从该用户开始调度
     */
    userId?: (string | null);
};

