/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TaskboardVersionStoryUpdate } from './TaskboardVersionStoryUpdate';
export type TaskboardVersionStoryIn = {
    /**
     * 本次取到的版本记录
     */
    records?: Array<TaskboardVersionStoryUpdate>;
    /**
     * 客户端观察时间，Unix 毫秒；用于丢弃旧批次
     */
    observed_at?: number;
};

