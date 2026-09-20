/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRManagedDroppedOverride = {
    /**
     * 被忽略的 Managed.Options 覆盖键
     */
    key: string;
    /**
     * 忽略原因：unknown=当前原生配置没有该字段；type=保存的值类型与原生配置不一致
     */
    reason: HSRManagedDroppedOverride.reason;
    /**
     * 用户保存的覆盖值
     */
    value?: any;
    /**
     * 人类可读说明
     */
    message?: string;
};
export namespace HSRManagedDroppedOverride {
    /**
     * 忽略原因：unknown=当前原生配置没有该字段；type=保存的值类型与原生配置不一致
     */
    export enum reason {
        UNKNOWN = 'unknown',
        TYPE = 'type',
    }
}

