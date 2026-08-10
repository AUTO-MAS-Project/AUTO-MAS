/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRCapabilityTask = {
    /**
     * 任务键
     */
    key: string;
    /**
     * 任务名称
     */
    name: string;
    /**
     * 任务阶段
     */
    phase: HSRCapabilityTask.phase;
    /**
     * 任务说明
     */
    description?: string;
    /**
     * 支持的执行引擎
     */
    engines?: Array<'M7A' | 'SRA'>;
    /**
     * 引擎策略
     */
    strategies?: Record<string, Array<string>>;
};
export namespace HSRCapabilityTask {
    /**
     * 任务阶段
     */
    export enum phase {
        DAILY = 'daily',
        WEEKLY = 'weekly',
    }
}

