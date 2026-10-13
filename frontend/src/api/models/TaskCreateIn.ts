/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskMode } from './TaskMode';
/**
 * 按设计 §5.1：mode + 可选 queue/script/user uid。
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
     * 用户 uid
     */
    userId?: (string | null);
};

