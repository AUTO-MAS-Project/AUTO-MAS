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
     * 任务计划的归属：script=脚本共享计划（保存到脚本配置），user=该用户自己的计划（保存到用户配置）
     */
    plan_owner?: HSRManagedConfigData.plan_owner;
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
export namespace HSRManagedConfigData {
    /**
     * 任务计划的归属：script=脚本共享计划（保存到脚本配置），user=该用户自己的计划（保存到用户配置）
     */
    export enum plan_owner {
        SCRIPT = 'script',
        USER = 'user',
    }
}

