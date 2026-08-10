/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRManagedTask } from './HSRManagedTask';
export type HSRManagedConfigData = {
    /**
     * 契约版本
     */
    revision?: string;
    /**
     * 托管任务
     */
    tasks?: Array<HSRManagedTask>;
    /**
     * 任务到引擎映射
     */
    task_mapping?: Record<string, 'M7A' | 'SRA'>;
    /**
     * 兼容性警告
     */
    warnings?: Array<string>;
};

