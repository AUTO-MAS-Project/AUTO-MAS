/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskIndexItem } from './TaskIndexItem';
import type { TaskItemDocument } from './TaskItemDocument';
export type TaskGetOut = {
    /**
     * 状态码
     */
    code?: number;
    /**
     * 操作状态
     */
    status?: string;
    /**
     * 操作消息
     */
    message?: string;
    index?: Array<TaskIndexItem>;
    data?: Record<string, TaskItemDocument>;
};

