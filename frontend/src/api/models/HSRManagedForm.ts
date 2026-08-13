/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRManagedField } from './HSRManagedField';
export type HSRManagedForm = {
    /**
     * 任务键
     */
    key?: (string | null);
    /**
     * 表单引擎
     */
    engine: HSRManagedForm.engine;
    /**
     * 表单字段
     */
    fields?: Array<HSRManagedField>;
    /**
     * 字段来源
     */
    source?: (string | null);
    /**
     * 表单警告
     */
    warnings?: Array<string>;
};
export namespace HSRManagedForm {
    /**
     * 表单引擎
     */
    export enum engine {
        M7A = 'M7A',
        SRA = 'SRA',
    }
}

