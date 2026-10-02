/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HSRManagedFieldVisibleWhen } from './HSRManagedFieldVisibleWhen';
export type HSRManagedField = {
    /**
     * 字段键
     */
    key: string;
    /**
     * 字段名称
     */
    label?: string;
    /**
     * 字段类型
     */
    type?: string;
    /**
     * 字段当前值
     */
    value?: any;
    /**
     * 字段说明
     */
    description?: (string | null);
    /**
     * 字段选项
     */
    options?: Array<any>;
    /**
     * 最小值
     */
    minimum?: (number | null);
    /**
     * 最大值
     */
    maximum?: (number | null);
    /**
     * 是否只读
     */
    readonly?: boolean;
    /**
     * 字段分组：common 平铺，其余各成一个默认收起的折叠面板
     */
    group?: HSRManagedField.group;
    /**
     * 当前计划（plan_owner 指向的那份）对该字段有生效中的覆盖值
     */
    overridden?: boolean;
    /**
     * 引擎原生配置里的值
     */
    native_value?: any;
    /**
     * 只有同模块同引擎里字段 key 的当前值在 values 中时才显示
     */
    visible_when?: (HSRManagedFieldVisibleWhen | null);
};
export namespace HSRManagedField {
    /**
     * 字段分组：common 平铺，其余各成一个默认收起的折叠面板
     */
    export enum group {
        COMMON = 'common',
        TEAM = 'team',
        SUPPORT = 'support',
        ACTIVITY = 'activity',
        REPLENISH = 'replenish',
        REROLL = 'reroll',
        MISC = 'misc',
    }
}

