/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRManagedDroppedOverride } from './HSRManagedDroppedOverride';
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
     * 表单级人类可读提示（如缺少配置说明文件），不含失效覆盖记录
     */
    warnings?: Array<string>;
    /**
     * 在当前原生配置中失效、运行时会被忽略的 Managed.Options 覆盖值
     */
    dropped_overrides?: Array<HSRManagedDroppedOverride>;
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

